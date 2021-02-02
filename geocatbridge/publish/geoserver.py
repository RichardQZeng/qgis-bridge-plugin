import os
import sqlite3
import webbrowser
from zipfile import ZipFile
from requests.exceptions import HTTPError

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import QgsProject, QgsDataSourceUri

from bridgestyle.qgis import saveLayerStyleAsZippedSld
from .exporter import exportLayer
from .serverbase import ServerBase
from ..utils import layers as layerUtils
from ..utils.files import tempFilenameInTempFolder
from ..utils.services import addServicesForGeodataServer


class GeoserverServer(ServerBase):
    FILE_BASED = 0
    POSTGIS_MANAGED_BY_BRIDGE = 1
    POSTGIS_MANAGED_BY_GEOSERVER = 2

    def __init__(self, name, url="", authid="", storage=0, postgisdb=None, useOriginalDataSource=False):
        super().__init__()
        self.name = name

        self.url = url.rstrip("/")
        if not self.url.endswith("/rest"):
            self.url += "/rest"

        self.authid = authid
        self.storage = storage
        self.postgisdb = postgisdb
        self.useOriginalDataSource = useOriginalDataSource
        self._isMetadataCatalog = False
        self._isDataCatalog = True
        self._layersCache = {}

    @property
    def _workspace(self):
        """ Returns the QGIS project name if the file has been saved. """
        path = QgsProject.instance().absoluteFilePath()
        if path:
            # Return project name from file path with spaces replaced by underscores
            return (os.path.splitext(os.path.basename(path))[0]).replace(' ', '_')
        return ""

    def prepareForPublishing(self, onlySymbology):
        if not onlySymbology:
            self.clearWorkspace()
        self._ensureWorkspaceExists()
        self._uploadedDatasets = {}
        self._exportedLayers = {}
        self._postgisDatastoreExists = False

    def publishStyle(self, layer):
        lyr_title, lyr_name = layerUtils.getLayerTitleAndName(layer)
        export_layer = layerUtils.getExportableLayer(layer, lyr_name)
        styleFilename = tempFilenameInTempFolder(lyr_name + ".zip")
        warnings = saveLayerStyleAsZippedSld(export_layer, styleFilename)
        for w in warnings:
            self.logWarning(w)
        self.logInfo(QCoreApplication.translate("GeocatBridge", "Style for layer '%s' exported as ZIP file to '%s'")
                     % (lyr_title, styleFilename))
        self._publishStyle(lyr_name, styleFilename)
        return styleFilename

    def publishLayer(self, layer, fields=None):
        lyr_title, safe_name = layerUtils.getLayerTitleAndName(layer)
        if layer.type() == layer.VectorLayer:
            if layer.featureCount() == 0:
                self.logError("Layer '%s' contains zero features and cannot be published" % lyr_title)
                return

            if layer.dataProvider().name() == "postgres" and self.useOriginalDataSource:
                from .postgis import PostgisServer
                uri = QgsDataSourceUri(layer.source())
                db = PostgisServer("temp", uri.authConfigId(), uri.host(), uri.port(), uri.schema(), uri.database())
                self._publishVectorLayerFromPostgis(layer, db)
            elif self.storage in [self.FILE_BASED, self.POSTGIS_MANAGED_BY_GEOSERVER]:
                src_path, src_name, src_ext = layerUtils.getLayerSourceInfo(layer)
                filename = self._exportedLayers.get(src_path)
                if not filename:
                    if self.storage == self.POSTGIS_MANAGED_BY_GEOSERVER:
                        shp_name = exportLayer(layer, fields, toShapefile=True, force=True, log=self)
                        basename = os.path.splitext(shp_name)[0]
                        filename = basename + ".zip"
                        with ZipFile(filename, 'w') as z:
                            for ext in (".shp", ".shx", ".prj", ".dbf"):
                                filetozip = basename + ext
                                z.write(filetozip, arcname=os.path.basename(filetozip))
                    else:
                        filename = exportLayer(layer, fields, log=self)
                self._exportedLayers[src_path] = filename
                if self.storage == self.FILE_BASED:
                    self._publishVectorLayerFromFile(layer, filename)
                else:
                    self._publishVectorLayerFromFileToPostgis(layer, filename)
            elif self.storage == self.POSTGIS_MANAGED_BY_BRIDGE:
                try:
                    from .servers import allServers
                    db = allServers()[self.postgisdb]
                except KeyError:
                    raise Exception(
                        QCoreApplication.translate("GeocatBridge", "Cannot find the selected PostGIS database"))
                db.importLayer(layer, fields)
                self._publishVectorLayerFromPostgis(layer, db)
        elif layer.type() == layer.RasterLayer:
            if layer.source() not in self._exportedLayers:
                path = exportLayer(layer, fields, log=self)
                self._exportedLayers[layer.source()] = path
            filename = self._exportedLayers[layer.source()]
            self._publishRasterLayer(filename, safe_name)
        self._clearCache()

    def _getPostgisDatastores(self, ds_list_url=None):
        """
        Finds all PostGIS datastores for a certain workspace (typically only 1).
        If `ds_url` is not specified, the first PostGIS datastore for the current workspace is returned.
        Otherwise, `ds_url` should be the datastores REST endpoint to a specific workspace.

        :param ds_list_url: REST URL that returns a list of datastores for a specific workspace.
        :returns:           A generator with PostGIS datastore names.
        """

        if not ds_list_url:
            ds_list_url = "%s/workspaces/%s/datastores.json" % (self.url, self._workspace)

        res = self.request(ds_list_url).json().get("dataStores", {})
        if not res:
            # There aren't any dataStores for the given workspace
            return

        for ds_url in (s.get("href") for s in res.get("dataStore", [])):
            ds = self.request(ds_url).json().get("dataStore", {})
            ds_name, enabled, params = ds.get("name"), ds.get("enabled"), ds.get("connectionParameters", {})
            # Only yield dataStore if it is enabled and the "dbtype" parameter equals "postgis"
            # Using the "type" property does not work in all cases (e.g. for JNDI connection pools or NG)
            entries = {e["@key"]: e["$"] for e in params.get("entry", [])}
            if enabled and entries.get("dbtype").startswith("postgis"):
                yield ds_name

    def createPostgisDatastore(self):
        """
        Creates a new datastore based on the selected one in the Server widget if the workspace is created from scratch.

        :returns:   The existing or created PostGIS datastore name.
        """

        # Check if current workspaces has a PostGIS datastore (use first)
        for ds_name in self._getPostgisDatastores():
            return ds_name

        # Get workspace and datastore name from selected template in Server widget
        ws, ds_name = self.postgisdb.split(":")

        # Retrieve settings from datastore template
        url = "%s/workspaces/%s/datastores/%s.json" % (self.url, ws, ds_name)
        datastore = self.request(url).json()
        # Change datastore name to match workspace name
        datastore["dataStore"]["name"] = self._workspace
        # Change workspace settings to match the one for the current project
        datastore["dataStore"]["workspace"] = {
          "name": self._workspace,
          "href": "%s/workspaces/%s.json" % (self.url, self._workspace)
        }
        # Fix featureTypes endpoint
        datastore["dataStore"]["featureTypes"] = "%s/workspaces/%s/datastores/%s/featuretypes.json" % (self.url, self._workspace, self._workspace)
        # Fix namespace connection parameter for current workspace
        self._fixNamespaceParam(datastore["dataStore"].get("connectionParameters", {}))
        # Post copy of datastore with modified workspace
        url = "%s/workspaces/%s/datastores.json" % (self.url, self._workspace)
        self.request(url, datastore, "post")
        return self._workspace

    def testConnection(self):
        try:
            url = "%s/about/version" % self.url
            self.request(url)
            return True
        except HTTPError:
            return False

    def unpublishData(self, layer):
        self.deleteLayer(layer.name())
        self.deleteStyle(layer.name())

    def baseUrl(self):
        return "/".join(self.url.split("/")[:-1])

    def _publishVectorLayerFromFile(self, layer, filename):
        self.logInfo("Publishing layer from file: %s" % filename)
        title, name = layerUtils.getLayerTitleAndName(layer)
        isDataUploaded = filename in self._uploadedDatasets
        if not isDataUploaded:
            with open(filename, "rb") as f:
                self._deleteDatastore(name)
                url = "%s/workspaces/%s/datastores/%s/file.gpkg?update=overwrite" % (self.url, self._workspace, name)
                self.request(url, f.read(), "put")
            conn = sqlite3.connect(filename)
            cursor = conn.cursor()
            cursor.execute("SELECT table_name FROM gpkg_geometry_columns")
            tablename = cursor.fetchall()[0][0]
            self._uploadedDatasets[filename] = (name, tablename)

        datasetName, geoserverLayerName = self._uploadedDatasets[filename]
        url = "%s/workspaces/%s/datastores/%s/featuretypes/%s.json" % (
            self.url, self._workspace, datasetName, geoserverLayerName)
        r = self.request(url)
        ft = r.json()
        ft["featureType"]["name"] = name
        ft["featureType"]["title"] = title
        ext = layer.extent()
        ft["featureType"]["nativeBoundingBox"] = {
            "minx": round(ext.xMinimum(), 5),
            "maxx": round(ext.xMaximum(), 5),
            "miny": round(ext.yMinimum(), 5),
            "maxy": round(ext.yMaximum(), 5),
            "srs": layer.crs().authid()
        }
        if isDataUploaded:
            url = "%s/workspaces/%s/datastores/%s/featuretypes" % (self.url, self._workspace, datasetName)
            self.request(url, ft, "post")
        else:
            self.request(url, ft, "put")
        self.logInfo("Successfully created feature type from GeoPackage file '%s'" % filename)
        self._setLayerStyle(name)

    def _publishVectorLayerFromPostgis(self, layer, db):
        name = layer.name()
        username, password = db.getCredentials()

        def _entry(k, v):
            return {"@key": k, "$": v}

        ds = {
            "dataStore": {
                "name": name,
                "type": "PostGIS",
                "enabled": True,
                "connectionParameters": {
                    "entry": [
                        _entry("schema", db.schema),
                        _entry("port", str(db.port)),
                        _entry("database", db.database),
                        _entry("passwd", password),
                        _entry("user", username),
                        _entry("host", db.host),
                        _entry("dbtype", "postgis")
                    ]
                }
            }
        }
        dsUrl = "%s/workspaces/%s/datastores/" % (self.url, self._workspace)
        self.request(dsUrl, data=ds, method="post")
        ft = {
            "featureType": {
                "name": name,
                "srs": layer.crs().authid()
            }
        }
        ftUrl = "%s/workspaces/%s/datastores/%s/featuretypes" % (self.url, self._workspace, name)
        self.request(ftUrl, data=ft, method="post")
        self._setLayerStyle(name)

    def _getImportResult(self, importId, taskId):
        """ Get the error message on the import task (if any) and the resulting layer name. """
        task = self.request("%s/imports/%s/tasks/%s" % (self.url, importId, taskId)).json()["task"] or {}
        err_msg = task.get("errorMessage", "")
        if err_msg:
            err_msg = "GeoServer Importer Extension error:\n%s" % err_msg
        return err_msg, task["layer"]["name"]

    def _publishVectorLayerFromFileToPostgis(self, layer, filename):
        self.logInfo("Publishing layer from file `%s`" % filename)
        datastore = self.createPostgisDatastore()
        title, ft_name = layerUtils.getLayerTitleAndName(layer)
        source_name = os.path.splitext(os.path.basename(filename))[0]

        # Create a new import
        body = {
            "import": {
                "targetStore": {
                    "dataStore": {
                        "name": datastore
                    }
                },
                "targetWorkspace": {
                    "workspace": {
                        "name": self._workspace
                    }
                }
            }
        }
        url = "%s/imports.json" % self.url
        ret = self.request(url, body, "post")

        # Create a new task and upload ZIP
        self.logInfo("Uploading layer data...")
        importId = ret.json()["import"]["id"]
        zipname = os.path.basename(filename)
        url = "%s/imports/%s/tasks/%s" % (self.url, importId, zipname)
        with open(filename, "rb") as f:
            ret = self.request(url, method="put", files={zipname: (zipname, f, 'application/octet-stream')})

        # Reassign PostGIS datastore as target (just to be sure)
        taskId = ret.json()["task"]["id"]
        body = {
            "dataStore": {
                "name": datastore
            }
        }
        url = "%s/imports/%s/tasks/%s/target.json" % (self.url, importId, taskId)
        self.request(url, body, "put")
        del ret

        # Start import execution
        self.logInfo("Starting Importer task for layer '%s'..." % ft_name)
        url = "%s/imports/%s" % (self.url, importId)
        self.request(url, method="post")

        # Get the import result (error message and target layer name)
        import_err, tmp_name = self._getImportResult(importId, taskId)
        if import_err:
            self.logError("Failed to publish QGIS layer '%s' as '%s'.\n\n%s" % (title, ft_name, import_err))
            return

        self._uploadedDatasets[filename] = (datastore, source_name)

        # Get the created feature type
        self.logInfo("Checking if feature type creation was successful...")
        url = "%s/workspaces/%s/datastores/%s/featuretypes/%s.json" % (self.url, self._workspace, datastore, tmp_name)
        try:
            ret = self.request(url + "?quietOnNotFound=true")
        except HTTPError as e:
            # Try to remove unwanted global style (created by Importer)
            try:
                self._fixLayerStyle(tmp_name, ft_name)
            except Exception as e:
                self.logWarning("Failed to perform global style cleanup:\n%s" % e)

            # Something unexpected happened: failure cannot be retrieved from import task,
            # so the user should check the GeoServer logs to find out what caused it.
            if e.response.status_code == 404:
                self.logError("Failed to publish QGIS layer '%s' as '%s' due to an unknown error.\n"
                              "Please check the GeoServer logs." % (title, ft_name))
                return
            raise

        # Modify the feature type descriptions, but leave the name in tact to avoid db schema mismatches
        self.logInfo("Fixing feature type properties...")
        ft = ret.json()
        ft["featureType"]["nativeName"] = tmp_name          # name given by Importer extension
        ft["featureType"]["originalName"] = source_name     # source file name
        ft["featureType"]["title"] = title                  # layer name as displayed in QGIS
        self.request(url, ft, "put")

        self.logInfo("Successfully created feature type from file '%s'" % filename)

        # Fix layer style reference and remove unwanted global style
        self.logInfo("Performing style cleanup...")
        try:
            self._fixLayerStyle(tmp_name, ft_name)
        except Exception as e:
            self.logWarning("Failed to fix layer style:\n%s" % e)

    def _publishRasterLayer(self, filename, layername):
        self._ensureWorkspaceExists()
        with open(filename, "rb") as f:
            url = "%s/workspaces/%s/coveragestores/%s/file.geotiff" % (self.url, self._workspace, layername)
            self.request(url, f.read(), "put")
        self.logInfo("Successfully created coverage from TIFF file '%s'" % filename)
        self._setLayerStyle(layername)

    def createGroups(self, groups):
        for group in groups:
            self._publishGroup(group)

    def _publishGroup(self, group):
        layers = []
        for layer in group["layers"]:
            if isinstance(layer, dict):
                layers.append({"@type": "layerGroup", "name": "%s:%s" % (self._workspace, layer["name"])})
                self._publishGroup(layer)
            else:
                layers.append({"@type": "layer", "name": "%s:%s" % (self._workspace, layer)})

        groupdef = {"layerGroup": {"name": group["name"],
                                   "title": group["title"],
                                   "abstractTxt": group["abstract"],
                                   "mode": "NAMED",
                                   "publishables": {"published": layers}}}

        url = "%s/workspaces/%s/layergroups" % (self.url, self._workspace)
        try:
            self.request(url, groupdef, "post")
        except:
            self.request(url, groupdef, "put")

        self.logInfo("Successfully created group '%s'" % group["name"])

    def deleteStyle(self, name):
        url = "%s/workspaces/%s/styles/%s?purge=true&recurse=true" % (self.url, self._workspace, name)
        try:
            self.request(url, method="delete")
        except HTTPError as e:
            # Swallow error if style does not exist (404), re-raise otherwise
            if e.response.status_code != 404:
                raise

    def _clearCache(self):
        self._layersCache = None

    def _exists(self, url, category, name):
        try:
            if category != "layer" or self._layersCache is None:
                r = self.request(url)
                root = r.json()["%ss" % category]
                if category in root:
                    items = [s["name"] for s in root[category]]
                    if category == "layer":
                        self._layersCache = items
                else:
                    return False
            else:
                items = self._layersCache
            return name in items
        except:
            return False

    def _getNextFeatureTypeName(self, datastore, name):
        """
        GeoServer never really removes a feature type. It appends a numeric suffix instead.
        This function tries to figure out what the next numeric suffix will be in case the name already exists.
        """
        url = "%s/workspaces/%s/datastores/%s/featuretypes.json?list=all" % (self.url, self._workspace, datastore)
        try:
            ftypes = sorted(self.request(url).json().get("list", {}).get("string", []))
        except HTTPError as e:
            if e.response.status_code == 404:
                # Workspace and/or datastore does not exist yet, so proposed name can be returned as-is
                return name
            raise

        # Find the next available numeric suffix
        numsuffix = -1
        for ft in ftypes:
            if not ft.startswith(name):
                continue
            suffix = ft[len(name):]
            if suffix.isnumeric():
                numsuffix = max(numsuffix, int(suffix))
        return name + (str(numsuffix + 1) if numsuffix >= 0 else "")

    def layerExists(self, name):
        url = "%s/workspaces/%s/layers.json" % (self.url, self._workspace)
        return self._exists(url, "layer", name)

    def layers(self):
        url = "%s/workspaces/%s/layers.json" % (self.url, self._workspace)
        r = self.request(url)
        root = r.json()["layers"]
        if "layer" in root:
            return [s["name"] for s in root["layer"]]
        else:
            return []

    def styleExists(self, name):
        url = "%s/workspaces/%s/styles.json" % (self.url, self._workspace)
        return self._exists(url, "style", name)

    def workspaceExists(self):
        url = "%s/workspaces.json" % self.url
        return self._exists(url, "workspace", self._workspace)

    def willDeleteLayersOnPublication(self, toPublish):
        if self.workspaceExists():
            return bool(set(self.layers()) - set(toPublish))
        return False

    def datastoreExists(self, name):
        url = "%s/workspaces/%s/datastores.json" % (self.url, self._workspace)
        return self._exists(url, "dataStore", name)

    def _deleteDatastore(self, name):
        url = "%s/workspaces/%s/datastores/%s?recurse=true" % (self.url, self._workspace, name)
        try:
            self.request(url, method="delete")
        except HTTPError as e:
            # Swallow error if datastore does not exist (404), re-raise otherwise
            if e.response.status_code != 404:
                raise

    def deleteLayer(self, name, recurse=True):
        param = '?recurse=true' if recurse else ""
        url = "%s/workspaces/%s/layers/%s.json%s" % (self.url, self._workspace, name, param)
        try:
            self.request(url, method="delete")
        except HTTPError as e:
            # Swallow error if layer does not exist (404), re-raise otherwise
            if e.response.status_code != 404:
                raise

    def openPreview(self, names, bbox, srs):
        url = self.layerPreviewUrl(names, bbox, srs)
        webbrowser.open_new_tab(url)

    def layerPreviewUrl(self, names, bbox, srs):
        baseurl = self.baseUrl()
        names = ",".join(["%s:%s" % (self._workspace, name) for name in names])
        url = (
                "%s/%s/wms?service=WMS&version=1.1.0&request=GetMap&layers=%s&format=application/openlayers&bbox=%s&srs=%s&width=800&height=600"
                % (baseurl, self._workspace, names, bbox, srs))
        return url

    def fullLayerName(self, layerName):
        return "%s:%s" % (self._workspace, layerName)

    def layerWmsUrl(self):
        return "%s/wms?service=WMS&version=1.1.0&request=GetCapabilities" % (self.baseUrl())

    def layerWfsUrl(self):
        return "%s/wfs" % (self.baseUrl())

    def setLayerMetadataLink(self, name, url):
        layerUrl = "%s/workspaces/%s/layers/%s.json" % (self.url, self._workspace, name)
        r = self.request(layerUrl)
        resourceUrl = r.json()["layer"]["resource"]["href"]
        r = self.request(resourceUrl)
        layer = r.json()
        key = "featureType" if "featureType" in layer else "coverage"
        layer[key]["metadataLinks"] = {
            "metadataLink": [
                {
                    "type": "text/html",
                    "metadataType": "ISO19115:2003",
                    "content": url
                }
            ]
        }
        self.request(resourceUrl, data=layer, method="put")

    def clearWorkspace(self):
        """
        Clears all feature types and coverages (rasters) and their corresponding layers.
        Leaves styles and datastore definitions in tact.
        """
        if not self.workspaceExists():
            # Nothing to delete: workspace does not exist yet (so let's create it)
            self._createWorkspace()
            return

        # Get database datastores configuration
        db_stores = []
        url = "%s/workspaces/%s/datastores.json" % (self.url, self._workspace)
        stores = self.request(url).json()["dataStores"] or {}
        for store in stores.get("dataStore", []):
            url = "%s/workspaces/%s/datastores/%s.json" % (self.url, self._workspace, store["name"])
            ds = self.request(url).json()
            params = ds["dataStore"].get("connectionParameters", {})
            if any(entry["@key"] == "dbtype" for entry in params.get("entry", [])):
                # Fix namespace
                if self._fixNamespaceParam(params):
                    self.request(url, ds, "put")
                # Store copy of datastore configuration if it's a database
                db_stores.append(dict(ds))

        # Remove all styles with purge=true option to prevent SLD leftovers
        url = "%s/workspaces/%s/styles.json" % (self.url, self._workspace)
        styles = self.request(url).json()["styles"] or {}
        for style in styles.get("style", []):
            url = "%s/workspaces/%s/styles/%s.json?recurse=true&purge=true" % (self.url, self._workspace, style["name"])
            self.request(url, method="delete")

        # Delete workspace recursively
        url = "%s/workspaces/%s.json?recurse=true" % (self.url, self._workspace)
        self.request(url, method="delete")

        # Recreate the workspace
        self._createWorkspace()

        # Add all database datastores
        for body in db_stores:
            url = "%s/workspaces/%s/datastores.json" % (self.url, self._workspace)
            self.request(url, body, "post")

        self._clearCache()

    def _fixNamespaceParam(self, params):
        """
        Fixes the namespace connection parameter to match the namespace URI for the current workspace.
        If the fix was applied successfully, True is returned.
        """
        for entry in params.get("entry", []):
            if entry["@key"] != "namespace":
                continue
            # Get expected namespace endpoint
            url = "%s/namespaces/%s.json" % (self.url, self._workspace)
            try:
                ns = self.request(url).json()
            except HTTPError:
                self.logWarning("GeoServer namespace '%s' does not exist")
                return False
            entry["$"] = ns["namespace"]["uri"]
            return True
        return False

    def _publishStyle(self, name, styleFilename):
        # feedback.setText("Publishing style for layer %s" % name)
        self._ensureWorkspaceExists()
        headers = {'Content-Type': 'application/zip'}
        if self.styleExists(name):
            # Update style
            method = "put"
            url = self.url + "/workspaces/%s/styles/%s" % (self._workspace, name)
        else:
            # Create new style
            url = self.url + "/workspaces/%s/styles?name=%s" % (self._workspace, name)
            method = "post"
        with open(styleFilename, "rb") as f:
            self.request(url, f.read(), method, headers)
        self.logInfo(QCoreApplication.translate("GeocatBridge", "Successfully created style '%s' from ZIP file '%s'"
                                                % (name, styleFilename)))

    def _setLayerStyle(self, name):
        url = "%s/workspaces/%s/layers/%s.json" % (self.url, self._workspace, name)
        layer = self.request(url).json()
        styleUrl = "%s/workspaces/%s/styles/%s.json" % (self.url, self._workspace, name)
        # TODO: does this still work properly?
        layer["layer"]["defaultStyle"] = {
            "name": name,
            "href": styleUrl
        }
        self.request(url, data=layer, method="put")

    def _fixLayerStyle(self, tmp_name, new_name):
        """
        Fixes the layer style for feature types that have been imported using the GeoServer Importer extension.
        The Importer extension also creates an unwanted global style, which is removed by this function.
        """

        # Get layer properties
        url = "%s/workspaces/%s/layers/%s.json" % (self.url, self._workspace, tmp_name)
        try:
            layer = self.request(url).json()
        except HTTPError:
            # This should not happen, because the layer inherits the feature type name.
            # In case that goes wrong, we could try fetching the layer using the new name.
            url = "%s/workspaces/%s/layers/%s.json" % (self.url, self._workspace, new_name)
            layer = self.request(url).json()

        # Get the URL of the unwanted global style that we need to clean up
        remove_url = "%s?recurse=true&purge=true" % layer["layer"]["defaultStyle"]["href"]

        # Assign desired workspace style (and name)
        layer["layer"]["name"] = new_name
        layer["layer"]["defaultStyle"] = {
            "name": "%s:%s" % (self._workspace, new_name)   # use workspace:name as identifier
        }
        self.request(url, data=layer, method="put")

        # Remove unwanted global style created by Importer extension (if exists)
        try:
            self.request(remove_url, method="delete")
        except HTTPError:
            pass

    def _createWorkspace(self):
        """ Creates the workspace. """
        url = "%s/workspaces" % self.url
        ws = {"workspace": {"name": self._workspace}}
        self.request(url, data=ws, method="post")

    def _ensureWorkspaceExists(self):
        if not self.workspaceExists():
            self._createWorkspace()

    def postgisDatastores(self):
        pg_datastores = []
        url = "%s/workspaces.json" % self.url
        res = self.request(url).json().get("workspaces", {})
        if not res:
            # There aren't any workspaces (and thus no dataStores)
            return pg_datastores
        for ws_url in (s.get("href") for s in res.get("workspace", [])):
            props = self.request(ws_url).json().get("workspace", {})
            ws_name, ds_list_url = props.get("name"), props.get("dataStores")
            for ds_name in self._getPostgisDatastores(ds_list_url):
                pg_datastores.append("%s:%s" % (ws_name, ds_name))
        return pg_datastores

    def addPostgisDatastore(self, datastoreDef):
        url = "%s/workspaces/%s/datastores" % (self.url, self._workspace)
        self.request(url, data=datastoreDef, method="post")

    def addOGCServers(self):
        baseurl = "/".join(self.url.split("/")[:-1])
        addServicesForGeodataServer(self.name, baseurl, self.authid)

    # ensure that the geoserver we are dealing with is at least 2.13.2
    def checkMinGeoserverVersion(self, errors):
        try:
            url = "%s/about/version.json" % self.url
            result = self.request(url).json()['about']['resource']
        except:
            errors.add("Could not connect to Geoserver.  Please check the server settings (including password).")
            return
        try:
            ver = next((x["Version"] for x in result if x["@name"] == 'GeoServer'), None)
            if ver is None:
                return  # couldn't find version -- dev GS, lets say its ok
            ver_major, ver_minor, ver_patch = ver.split('.')

            if int(ver_minor) <= 13:
                # GeoServer instance is too old
                errors.add(
                    "Geoserver 2.14.0 or later is required. Selected Geoserver is version '" + ver + "'. "
                    "Please see <a href='https://my.geocat.net/knowledgebase/100/Bridge-4-compatibility-with-"
                    "Geoserver-2134-and-before.html'>Bridge 4 Compatibility with Geoserver 2.13.4 and before</a>"
                )
        except:
            # version format might not be the expected. This is usually a RC or dev version, so we consider it ok
            pass

    def validateGeodataBeforePublication(self, errors, toPublish, onlySymbology):
        if not self._workspace:
            errors.add("QGIS Project is not saved. Project must be saved before publishing layers to GeoServer.")
        if "." in self._workspace:
            errors.add("QGIS project name contains unsupported characters ('.'). "
                       "Please save with a different name and try again.")
        if self.willDeleteLayersOnPublication(toPublish) and not onlySymbology:
            ret = QMessageBox.question(None, "Workspace",
                                       "A workspace named '%s' already exists and contains layers that will be deleted."
                                       "\nDo you want to proceed?" % self._workspace,
                                       QMessageBox.Yes | QMessageBox.No)
            if ret == QMessageBox.No:
                errors.add("Cannot overwrite existing workspace.")
        self.checkMinGeoserverVersion(errors)
