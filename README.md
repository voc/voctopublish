This is a glue script that reads information from the C3TT [1] and talks to voctoweb [2], youtube [3], twitter [4] and mastodon [5].

It publishes recordings an handles all necessary steps like thumbnail generation

## Dependencies
### Debian / Ubuntu
```
sudo apt-get install python3 python3-requests python3-pip ffmpeg timelens
pip3 install -r requirements.txt
```

## Usage
use the provided client.conf.example to tell the script to which hosts it should talk. Most of the configuration is done in the tracker
Some examples for usefull properties can be found on [6]

"Viel Spaß am Gerät"


* [1] https://github.com/crs-tools/tracker
* [2] https://github.com/voc/voctoweb
* [3] https://www.youtube.com/yt/dev/de/api-resources.html
* [4] https://dev.twitter.com/rest/public
* [5] https://github.com/tootsuite/documentation/blob/master/Using-the-API/API.md
* [6] https://c3voc.de/wiki/c3tracker?s[]=tracker#tracker-project_and_worker
