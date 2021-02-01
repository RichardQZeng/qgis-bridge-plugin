Requirements
############

Client requirements
*******************

Bridge requires QGIS 3.6 or more recent.

Server requirements
*******************

GeoNetwork
----------

GeoCat Bridge is officially supported on any GeoNetwork latest (3.8)_ and
2 versions before (3.4 and 3.6)_. However most of the functionality will
be operational from GeoNetwork version 2.6+.

MapServer
---------

Requirement for MapServer are:

-   Officially supported is the latest minor version of MapServer and 2
    versions before, currently 7.0, 6.4 and 6.2. However, any version
    from 5.6.0 is expected to operate fine in most of the cases.
-   FTP connection or file write access to MapServer project path.


GeoServer
---------

Requirements for GeoServer are:

-   Officially supported versions are 2.15, 2.14 and 2.13. However, other
    versions since 2.4 are expected to operate fine in most of the
    cases.


Installation (Bridge Enterprise)
################################

To install Bridge Enterprise from the zip package provided by GeoCat, follow these steps:

1. Open the :guilabel:`QGIS Plugin Manager`. The Plugin Manager can be opened using the :menuselection:`Plugins-->Manage and install plugins` menu entry.

	.. image:: ./img/pluginmanagermenu.png

	You will see the following dialog:

	.. image:: ./img/pluginmanager.png

2. Select the :guilabel:`Install from zip` section.

	.. image:: ./img/installfromzip.png

3. Enter the path to the provided zip file by typing in the :guilabel:`ZIP file` text box, or click on the :guilabel:`...` button to browse your filesystem.

4. Click on the :guilabel:`Install plugin` button to install the plugin.

5. Click on :guilabel:`Close` button to close

6. Close the :guilabel:`Plugin Manager` and you will find a new menu entry under the :menuselection:`Web` menu, which contains the menus from the Bridge plugin.

	.. image:: ./img/bridgemenuentry.png

7. You will also find a new toolbar button.

	.. image:: ./img/bridgetoolbarbutton.png
