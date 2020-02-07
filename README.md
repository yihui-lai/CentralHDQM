# Table of contents

- [Central Historic DQM application for CMS detector](#central-historic-dqm-application-for-cms-detector)
- [Usage instructions](#usage-instructions)
  * [How to run locally](#how-to-run-locally)
  * [How to add new plots](#how-to-add-new-plots)
    + [Backend configuration](#backend-configuration)
    + [Frontend configuration](#frontend-configuration)
  * [Web application usage](#web-application-usage)
- [API documentation](#api-documentation)
  * [Endpoints](#endpoints)
    + [`/api/data`](#--api-data-)
    + [`/api/selection`](#--api-selection-)
    + [`/api/plot_selection`](#--api-plot-selection-)
    + [`/api/runs`](#--api-runs-)
    + [`/api/expand_url`](#--api-expand-url-)
- [Administration instructions](#administration-instructions)
  * [Daily extraction](#daily-extraction)
  * [How to update](#how-to-update)
    + [How to rollback to the old version](#how-to-rollback-to-the-old-version)

# Central Historic DQM application for CMS detector

A tool to display trends of CMS DQM quantities over long periods of time.  
The web application is available here: https://cms-hdqm-test.web.cern.ch  
The code is running on a `vocms0231` machine.

# Usage instructions

## How to run locally

The following instruction are completely copy-pastable. This will start a complete HDQM stack on your local (lxplus) environment. This is perfect for testing new plots before adding them. Instructions are are made for bash shell.

``` bash
# You have to change the username. From this point, all instruction can be copy pasted without modifications.
ssh -L 8000:localhost:8000 -L 8080:localhost:5000 <YOUR_USER_NAME>@lxplus7.cern.ch
/bin/bash
mkdir -p /tmp/$USER/hdqm
cd /tmp/$USER/hdqm/

git clone https://github.com/cms-dqm/CentralHDQM
cd CentralHDQM/

# Get an SSO to access OMS and RR APIs. This has to be done before cmsenv script
# First check if we are the owner of the folder where we'll be puting the cookie
if [ $(ls -ld /tmp/$USER/hdqm/CentralHDQM/backend/api/etc | awk '{ print $3 }') == $USER ]; then 
    cern-get-sso-cookie -u https://cmsoms.cern.ch/agg/api/v1/runs -o backend/api/etc/oms_sso_cookie.txt
    cern-get-sso-cookie -u https://cmsrunregistry.web.cern.ch/api/json_creation/generate -o backend/api/etc/rr_sso_cookie.txt
fi

cd backend/
# This will give us a CMSSW environment
source cmsenv

# Add python dependencies
python3 -m pip install -r requirements.txt -t .python_packages/python3
python -m pip install -r requirements.txt -t .python_packages/python2

export PYTHONPATH="${PYTHONPATH}:$(pwd)/.python_packages/python2"

cd extractor/

# Extract few DQM histograms. Using only one process because we are on SQLite
./hdqmextract.py -c cfg/PixelPhase1/trendPlotsPixelPhase1_tracks.ini -r 325117 325159 325168 325169 325170 325172 325175 325308 325309 325310 -j 1

# Calculate HDQM values from DQM histograms stored in the DB
./calculate.py -c cfg/PixelPhase1/trendPlotsPixelPhase1_tracks.ini -r 325117 325159 325168 325169 325170 325172 325175 325308 325309 325310 -j 1

# Get the OMS and RR data about the runs
./oms_extractor.py
./rr_extractor.py

cd ../api/
# Run the API
./run.sh &>/dev/null &

cd ../../frontend/
# Use local API instead of the production one
sed -i 's/\/api/http:\/\/localhost:8080\/api/g' js/config.js
# Run the static file server
python3 -m http.server 8000 &>/dev/null &

# Run this to find pids of running servers to kill them:
# ps awwx | grep python
```

That's it! Now visit http://localhost:8000/ on your browser.

## How to add new plots

In order to add new plots to HDQM, you have to provide two layers of configuration:  
1. backend configuration
2. frontend configuration

Configuration is all in code and in order to add new plots you have to make a pull request against this repo: https://github.com/cms-DQM/CentralHDQM

### Backend configuration

Backend is configured with `.cfg` files that describe what monitor elements should be taken from the DQM `.root` files and how the value from the should be extracted for plotting.  
These files are placed here, in a corresponding subsystem directory: `backend/extractor/cfg/<subsystem>`. This directory structure has to be preserved in order for the tool to work. 

Let's take a look at an example:

``` ini
[plot:Ntracks_Pixel]
metric = basic.BinCount(2)
relativePath = PixelPhase1/Tracks/ntracks
plotTitle = Pixel number of tracks
yTitle = Number of Tracks in Pixel
```

That's all it takes to tell HDQM how to plot a DQM quantity over time. Let's break this down line by line.

* The first line describes an ID of a plot that is unique per subsystem. This ID will be used to refer to this plot later on. *This field is required*.
* **metric** property tells the tool what function needs to be called to reduce a DQM histogram to a single value that will be plotted. Think of this as of a constructor call of a Python class. Classes that can be used are defined here: `backend/extractor/metrics/`. If necessary, new python classes could be added. new classes have to provide a constructor with as many arguments as it's required to be referred to from the configuration and a `calculate(self, histo)` method that will be called by the backend. This function has to return a tuple of two values `(value, error)`. *This field is required*.
* **relativePath** is a path of a monitor element in a legacy DQM root file that a metric should be applied to. In case a path of a monitor element changed, you can provide multiple, space separated paths here. ME that is found the first will be used. *This field is required*.
* **plotTitle** is a title of a plot that will be displayed in a web application. This value can contain spaces as it only has to be human readable. If this field is not provided, yTitle will be used instead. *This field is not required*.
* **yTitle** is a title of y axis. It is usually used to display the units used in a plot. *This field is required*.

Those were the main properties, however there are other less common ones:

``` ini
histo1Path = PixelPhase1/Phase1_MechanicalView/PXBarrel/num_clusters_PXLayer_2
histo2Path = PixelPhase1/Phase1_MechanicalView/PXBarrel/size_PXLayer_2
threshold = 50
```

* Sometimes, a value of a point in a trend depends on more than one DQM histogram. In such cases **histo1Path** and **histo2Path** could be used to define the paths of the other histograms. *These fields are not required*.
* **threshold** was used previously to define a minimum number of entries for a histogram to be taken into a trend. Now, this is no longer used, however this value can be wired in your custom Python extraction class. *This field is not required*.

### Frontend configuration

In a frontend configuration you can define what is called **display groups**. Display groups define a list of related plots that will be displayed together in a web application, as an overlay.  
The configuration is located here: `frontend/js/displayConfig.js`. All fields here are required!

Let's take a look at an example:

``` js
{
  name: "an_id_of_a_display_group",
  plot_title: "Nice, readable title of a group",
  y_title: "Units of all series in a group",
  subsystem: "<Subsystem>",
  correlation: false,
  series: ["plot1_ID", "plot2_ID"],
}
```

Let's break this down line by line.

* **name** is an ID of a display group. It has to be unique within all display groups and regular plots within a subsystem.
* **plot_title** is a title of a grouped plot that will be displayed in a web application. 
* **y_title** is a title of y axis of a grouped plot. It is usually used to display the units used in a plot.
* **subsystem** is the name of the subsystem. It has to match exactly the name of the folder where backend configuration files came from (`backend/extractor/cfg/<subsystem>`).
* **correlation** is a boolean value defining if the plot should be displayed in a correlation mode. This can be `true` only when there are exactly 2 series in a display group.
* **series** is an array if plot ID from backend configuration that will appear in a display group.

## Web application usage 

In a web application, user has to select the data first by selecting a **subsystem**, **primary dataset** and a **processing string** at a very top of the page and all plots present in selected data will be displayed.

Runs can be filtered in one of the following ways:

* Latest N runs
* Run range
* Comma separated list of runs
* Golden JSON file

By clicking **Options** button, a display mode of the plots can be chosen. Available display modes are:

* Scatter plot
* Bin width proportional to run duration
* Bin width proportional to integrated luminosity
* Datetime plot based on start and end times of runs
* Correlation plot

By clicking *Show / Change ranges* button a *full screen mode* of a plot will be entered. In a *full screen mode* you can do one of the following things:

* Change the X and Y ranges of a plot
* Click on runs (data points) and reveal more information about them in the right hand side panel
* See the DQM histogram(s) that was used to extract the value of a trend in the right hand side panel
* Look at a selected run in DQM GUI, OMS and Run Registry
* Add or remove series from the plot dynamically by clicking *Add series to this plot*

# API documentation

This very API is powering the web application. No other, hidden API services are used. The web page is all static - no server rendering. 

**All endpoints should be used by making an HTTP GET request and providing the arguments in the url.**

## Endpoints

* `/api/data` 
* `/api/selection`
* `/api/plot_selection`
* `/api/runs`
* `/api/expand_url`

Let's talk about each of them one by one.

### `/api/data` 

This is the main endpoint used to retrieve historic DQM data.

Possible arguments:

| Param             | Data type  | Required/Optional                                                                          | Description                                                                                             |
|-------------------|------------|--------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------|
| subsystem         | string     | required                                                                                   | Name of the subsystem. Possible values come from `/api/selection` endpoint.                            |
| pd                | string     | required                                                                                   | Name of the primary dataset. Possible values come from `/api/selection` endpoint.                      |
| processing_string | string     | required                                                                                   | Name of the processing string. Possible values come from `/api/selection` endpoint.                    |
| from_run          | int        | required together with `to_run`. Both can be substituted with either `runs` or `latest`.   | Runs filter: lower bound.                                                                               |
| to_run            | int        | required together with `from_run`. Both can be substituted with either `runs` or `latest`. | Runs filter: upper bound.                                                                               |
| runs              | array<int> | required but can be substituted with `from_run`, `to_run` or `latest`.                     | Runs filter: *comma separated* list of runs to return data for.                                           |
| latest            | int        | required but can be substituted with `from_run`, `to_run` or `runs`.                       | Runs filter: return latest N runs.                                                                      |
| series            | string     | optional                                                                                   | Specific name of the series to return. If not specified, all series will be returned based on selection. |
| series_id         | int        | optional                                                                                   | Specific series ID. IDs come from `/api/plot_selection` endpoint.                                       |

Keep in mind that runs can be filtered in 3 ways: 
* Range (`from_run`, `to_run`)
* List of specific runs (`runs`)
* Last N runs (`latest`)

**Exactly one way must be used to filter out required runs**.

Sample query: `/api/data?subsystem=PixelPhase1&pd=SingleElectron&processing_string=09Aug2019_UL2017&latest=50`

### `/api/selection` 

This endpoint returns a nested object of possible `subsystem`, `primary dataset` and `processing string` combinations. This endpoint takes no arguments.

Sample (shortened) response:

``` json
{
  "CSC":{
    "Cosmics":[
      "PromptReco"
    ],
    "JetHT":[
      "09Aug2019_UL2017"
    ]
  },
  "Muons":{
    "ZeroBias":[
      "09Aug2019_UL2017",
      "PromptReco"
    ]
  }
}
```

### `/api/plot_selection`

This endpoint is very similar to `/api/selection`, but it is one level deeper. It also includes the names and IDs of all available series. Names and IDs can be used to retrieve only **required** plots using `series` or `series_id` parameters in `/api/data` endpoint. This endpoint takes no arguments.

Sample (shortened) response:

``` json
{
  "CSC":{
    "Cosmics":{
      "PromptReco":[
        {
          "id":4426,
          "name":"AnodeCatodheTimeDiff"
        }
      ]
    }
  }
}
```

### `/api/runs`

This endpoint returns a list of all run numbers present in the HDQM database. This endpoint takes no arguments.

### `/api/expand_url`

For performance reasons, DQM GUI URLs for each data point are not returned by the `/api/data` endpoint. However, the data point IDs are returned and using this endpoint they can be exchanged for an actual DQM GUI URL.

Possible arguments:

| Param         | Data type | Required/optional | Description                                                                                                                                                                                                                      |
|---------------|-----------|-------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| data_point_id | int       | required          | An ID referring to a single data point returned by the `/api/data` endpoint.                                                                                                                                                     |
| url_type      | string    | required          | Type of the DQM GUI URL required. All possible values are: `main_gui_url`, `main_image_url`, `optional1_gui_url`, `optional1_image_url`, `optional2_gui_url`, `optional2_image_url`, `reference_gui_url`, `reference_image_url`. |

# Administration instructions

Production service is running on a public port 80 and test service on 81.
Production API server is running on internal port 5000 and test API service on 5001.

**Before doing anything become the correct user:**  
`sudo su hdqmpro`

Code is located in `/data/hdqm/` directory.

EOS and CVMFS file systems need to be accessible in order for the service to work. ROOT input files are coming EOS, and CMSSW release is comming from CVMFS.

Nginx configuration for a reverse proxy can be found here: `/etc/nginx/conf.d/`

Systemctl service for an API server can be found here: `/etc/systemd/system/hdqm.service`

Starting reverse proxy (nginx):
`sudo systemctl start nginx.service`

Starting an API service:  
`sudo systemctl start hdqm.service`

Packages are installed locally in `backend/.python_packages/python2` and `backend/.python_packages/python3` directories, for different python versions. Extractor and calculator are using python 2 as they rely on ROOT but an API Flask service is running on python 3. Make sure an appropriate python path is set before using the tools by hand. For example (running from `backend` directory):

```bash 
export PYTHONPATH="${PYTHONPATH}:$(pwd)/.python_packages/python2"
```

If nginx complains that it can't bind to port, make sure to request the ports to be opened in puppet:  
https://gitlab.cern.ch/ai/it-puppet-hostgroup-vocms/merge_requests/72  

And open them using SELinux: `sudo semanage port -m -t http_port_t -p tcp 8081`  
Also important:  
`sudo firewall-cmd --zone=public --add-port=81/tcp --permanent`  
`sudo firewall-cmd --reload`  
Make sure to make root directory accessible in SELinux:  
`chcon -Rt httpd_sys_content_t /data/hdqmTest/CentralHDQM/frontend/`  
`sudo chcon -Rt httpd_sys_content_t /data/hdqm/`

## Daily extraction

HDQM automatically extracts data from EOS on a daily basis. This is done using systemctl timer.  
A timer `hdqm-extract.timer` launches `hdqm-extract.service` service every day. In order to stop the timer run:  
```bash
sudo systemctl stop hdqm-extract.timer
```
To get info about a timer run one of these two commands:
```bash
sudo systemctl list-timers
sudo systemctl status hdqm-extract.timer
```

## How to update

The following script will pull a latest version of the HDQM code from a `https://github.com/cms-DQM/CentralHDQM` repository. It will copy required secret files from `private` directory, and point `current` symlink to the newly created version. 

```bash
ssh vocms0231
cd /data/hdqm
sudo su hdqmpro
./update.sh
exit
sudo systemctl restart hdqm.service
```

### How to rollback to the old version

In order to rollback to the previous version set `current` symlink to point to the required version folder (in the same directory) and restart the service:

```bash
cd /data/hdqm
ln -s -f -n <FOLDER_OF_THE_REQUIRED_VERSION> current
sudo systemctl restart hdqm.service
```
