This repository contains a glue script that reads information from the C3TT [1] and talks to voctoweb [2], youtube [3] and twitter [4].

It publishes recordings an handles all necessary steps like thumbnail generation

## Depencies
### Debian / Ubuntu
```
sudo apt-get install python3 python3-requests python3-pip ffmpeg
sudo pip3 install paramiko
```

## Usage
use the provided client.conf.example to tell the script to which hosts it should talk. Most of the configuration is done in the tracker

 * [1] TBA (the tracker will be publicly available soon)
 * [2] https://github.com/voc/voctoweb
 * [3] https://www.youtube.com/yt/dev/de/api-resources.html
 * [4] https://dev.twitter.com/rest/public


"Viel Spaß am Gerät"
