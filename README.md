# Linux Log Parser
## Description
This script automatically parses linux logs from triage outputs of various supported linux distributions to Filebeat. Filebeat will then ingest the logs directly to Elasticsearch thereafter.
There are two versions of the script in which it can be run on windows or linux systems. If you are working on a windows system, run the "windows_main.py". Likewise if you are working on a linux system, run the "linux_main.py" instead.
### ⚠️Note
Currently, the linux version of the Linux Log Parser is the stable release. Although the windows version is still a work in progress, it is still able to ingest the logs to Elasticsearch. However, Filebeat is unable to process them into syslog format which may end up giving unnecessary/unwanted columns when the logs are viewed on Elasticsearch.
## Filebeat Overview
Filebeat is a lightweight shipper for forwarding and centralizing log data. Installed as an agent on your servers, Filebeat monitors the log files or locations that you specify, collects log events, and forwards them either to Elasticsearch or Logstash for indexing.
## Running Linux Log Parser (For Linux systems)
```
$ python3 linux_main.py -h
usage: linux_main.py [-h] [-s SYS] [-u HOST] [-i INDEX] [-p [PATH]] ...

Parses Linux logs to ELK

positional arguments:
  DIR                   Specify directory path to extract and parse logs from

optional arguments:
  -h, --help            show this help message and exit
  -s SYS, --system SYS  Specify type of OS
  -u HOST, --url HOST   Specify the URL for Elasticsearch instance (Including port number)
  -i INDEX, --index INDEX
                        Specify the index on Elasticsearch
  -p [PATH], --path [PATH]
                        Specify the path for Filebeat directory
```
Before running the script, ensure that you have downloaded the latest version of Filebeat for Linux systems (64-bit) and unzipped into the same curent working directory of the script (recommended), which is in the *Linux Log Parser* directory.  
You may download Filebeat [here](https://www.elastic.co/downloads/beats/filebeat).

Once you have dowloaded Filebeat, you may run the script in a terminal.  
There are four required arguments that needs to be parsed for the script to run:
1. -s SYS, --system SYS
   - This switch specifies the OS type of the triage output that was collected from
2. -u HOST, --url HOST
   - This switch specifies the URL of the Elasticsearch instance that is being hosted on
3. -i INDEX, --index INDEX
   - This switch spcifies the name of the index for Filebeat to ingest the logs to on Elasticsearch
   - Filbeat will create a new index for it if does not exist in your Elasticsearch instance
4. DIR
   - The final required argument requires the directory path of the triage output to parse the logs from
   - The directory path of the triage output should be relative to the curent working directory of the script, which is the *Linux Log Parser* directory
   - You may specify more than one triage output of the same type of OS (Please run the script again for each type of OS)

Example:  
> Typical usage:  
`python3 linux_main.py -s ubuntu -u http://my-elk.instance.lab:9200 -i ubuntu_client_index ./ubuntu-triage_20211110_062835`  
> If there is more than one traige output of the same OS type:  
`python3 linux_main.py -s rhel7 -u http://my-elk.instance.lab:9200 -i rhel7_client_index ./centos7-triage_20211006_143423 ./centos7-triage_20210913_154539`

The following arguments below are optional arguments that may be included in the command line for the script to run:
1. -p [PATH], --path [PATH]
   - This switch specifies the directory path of Filebeat
   - The directory path of Filebeat should be relative to the curent working directory of the script, which is the *Linux Log Parser* directory

Example:  
> The file path for Filebeat is located outside of the current working directory:  
`python3 linux_main.py -s ubuntu -u http://my-elk.instance.lab:9200 -i ubuntu_collection_index -p ../../Downloads/filebeat-7.15.2-linux-x86_64 ./ubuntu-triage_20210731_231550`
