# Jamf Mobile Application Data to JSON

## Purpose
The purpose of this script is to sync mobile device applications via the Jamf Classic API and append various data elements to a primary JSON file that can be uploaded to a BI tool.

### Datapoints Collected for Mobile Devices Applications:
```
{
  "mobile_device_applications": [
    {
      "application_id": 87,
      "application_name": "MyApp",
      "bundle_id": "com.myapp.app",
      "devices": [
        {
          "device_id": "26",
          "application_version": "2.4.5",
          "application_status": "Managed"
        },
        {
          "device_id": "115",
          "application_version": "3.5",
          "application_status": "Managed"
        }
      ]
    }
  ]
}
```

Configure the .ENV file as follows:
```
JSSUSER = "api_user"
JSSPASS = "api_user_pw"
JSS = "https://myInstance.jamfcloud.com"
SERVERTYPE = "windows"
```


""""""
