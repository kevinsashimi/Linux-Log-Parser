# Linux Log Parser
## Description
This script automatically parses linux logs from triage outputs of various supported linux distributions to Filebeat. Filebeat will then ingest the logs directly to Elasticsearch thereafter.
There are two versions of the script in which it can be run on windows or linux systems. If you are working on a windows system, run the "windows_main.py". Likewise if you are working on a linux system, run the "linux_main.py" instead.
### Note
Currently, the linux version of the Linux Log Parser is the stable release. Although the windows version is still a work in progress, it is still able to ingest the logs to Elasticsearch. However, Filebeat is unable to process them into syslog format which may end up giving unnecessary/unwanted columns when the logs are viewed on Elasticsearch.

## Filebeat Overview
Filebeat is a lightweight shipper for forwarding and centralizing log data. Installed as an agent on your servers, Filebeat monitors the log files or locations that you specify, collects log events, and forwards them either to Elasticsearch or Logstash for indexing.

## Running Linux Log Parser (For Linux systems)
