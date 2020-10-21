# pythonCC
Accessing a On Premise system using a cloud connector from a Cloud Foundry python application

## 1. On Premise System
  * For convenience we are accessing SAP GitHub (github.wdf.sap.corp)
## 2. SAP Cloud Platform
  * Configure the SAP Cloud Connector for the global account
    ![SAP Cloud Connector](/images/CF_CC.PNG)
## 3. SAP Cloud Platform
  * Add destination in the account pointing the Cloud Connector
    > ![SAP Cloud Connector](/images/CF_DEST.PNG)
  * Deploy the application and bind the destination, XSUAA, Connectivity services to the application.
    > ![Service Bindings](/images/Service_Bindings.PNG)
  * Alter the service names in the 13th line of the `app.py` file
    > ![Service Names](/images/Service_Names.PNG)
  * Access the `getData` endpoint for getting data, and `downloadDir` for downloading the entire directory from Github.
    * pass the parameters `destination` and `path`
