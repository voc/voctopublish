#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os, sys
import lxml.etree
import ftputil, urllib, shutil
import configparser, argparse
import requests
 
cp = configparser.ConfigParser()
cp.read('tib.conf')
config = cp['TIB AV Portal']
 
parser = argparse.ArgumentParser(description='TIB AV Portal: Upload and metadata generation ') 
parser.add_argument('schedule', help='schedule.xml file name, path or HTTP URL')
parser.add_argument('--upload', action='store_true')
parser.add_argument('--verbose',  '-v', action='store_true', default=False)
args = parser.parse_args() 

# lxml does only supports http and not https, compare https://stackoverflow.com/a/26164472
#schedule = etree.fromstring(requests.get("https://events.ccc.de/congress/2017/Fahrplan/schedule.xml").content)
#schedule = lxml.etree.parse("temp/schedule.xml")
schedule = lxml.etree.parse(args.schedule)


# for new conferences we can use header field
frab_base_url = schedule.find('conference').find('base_url').text
# but older conferences might manuall setting:
#frab_base_url = 'https://events.ccc.de/congress/2017/Fahrplan/'

acronym = schedule.find('conference').find('acronym').text


host = ftputil.FTPHost(config['server'], config['user'], config['password']) 

dry_run = not args.upload
#TODO: use argument parser?
ignore_licence = True

def main():
    for event_id in schedule.xpath(u'day/room/event/@id'):
        event = schedule.xpath('day/room/event[@id="' + event_id + '"]')[0]
        title = event.find('title').text
        slug = event.find('slug').text.strip()
        #link = frab_base_url + '/events/{0}.html\n'.format(event_id)
        # The schedule.xml event has now (since 34C3) a own attriute containing the url to the event page:
        link = event.find('url').text

        if args.verbose:
            print('== ' + title)
        #print(event.find('room').text)


        if event.find('recording').find('optout').text == 'true':
            sys.stderr.write(" INFO: Ignoring '" + title + "' due to optout\n")
            continue


        # download file directly from our intermediate upload host. But not for C3...
        #file_url = 'http://live.ber.c3voc.de/releases/{}/{}-hd.mp4'.format(acronym, event_id)

        # request recording from voctoweb aka media.ccc.de
        recording = find_recoding(event.attrib['guid'])
        file_url = recording['recording_url']


        if not ignore_licence and event.find('recording').find('license').text is None:
            sys.stderr.write(" \033[91mERROR: " + title + " has empty recoding license \033[0m\n")
            continue

        with urllib.request.urlopen(file_url) as u:

            if u.getcode() != 200:
                sys.stderr.write(" \033[91mERROR: " + title + " is not available as mp4 file \033[0m\n")
                continue

            if not dry_run:
                if not host.path.exists(slug):
                    host.mkdir(slug)
                #host.upload_if_newer(local_path, slug + '/' + slug + '.mp4')
                # Maybe TODO: display upload progress?
                with host.open("{0}/{0}.mp4".format(slug), "wb") as f:
                    shutil.copyfileobj(u, f)


        # format person names to library conventions – random search result: https://books.google.de/books?id=wJyoBgAAQBAJ&pg=PA68&lpg=PA68&dq=bibliotheken+mehrere+vornamen&source=bl&ots=bP4gjj1Zft&sig=2HxD9qHWHzo7Z0kMc5vMITo83ps&hl=en&sa=X&redir_esc=y#v=onepage&q=bibliotheken%20mehrere%20vornamen&f=false
        persons = []
        for p in event.find('persons'):
            p = p.text.split(' ')
            if len(p) > 3:
                print("   \033[91mWARNING: Person name consits of more then three parts: " + str(p) + "\033[0m") 
            if len(p) == 1:
                persons.append(p[0])
            elif len(p) == 2:
                persons.append(p[1] + ', ' + p[0])
            else:
                persons.append(p[-1] + ', ' + p[0] + ' ' + p[1])


        # see https://github.com/voc/scripts/blob/master/slides/get_attachments.py
        # future TODO: upload pdf's from frab to ftp host
        material = []
        if os.path.isfile('temp/{}.pdf'.format(slug)):
            material.append(('File', 'Slides as PDF', '{}.pdf'.format(slug)))
        for a in event.find('attachments'):
            path = a.attrib['href'].split('?')[0]
            basename = os.path.basename(path)
            local_path = 'temp/{}/{}'.format(slug, basename)
            if os.path.isfile(local_path):
                if not dry_run: host.upload_if_newer(local_path, slug + '/' + basename)
                material.append(('File', a.text, slug + '/' + basename))
            elif path != '/attachments/original/missing.png':
                material.append(('URL', a.text, frab_base_url+path))

        lang = event.find('language').text
        if lang == 'en':
            lang = 'eng'
        elif lang == 'de':
            lang = 'ger'

        abstract = event.find('abstract').text 
        if not abstract:
            # use description when abstract is empty
            abstract = event.find('description').text
        if not abstract:
            sys.stderr.write(" \033[91mFATAL: " + title + " has empty abstract \033[0m\n")
            exit()
        abstract = strip_tags(abstract) 

        f = None
        if dry_run:
            f = open("temp/{}.xml".format(slug), "wt")
        else:
            f = host.open("{0}/{0}.xml".format(slug), "w", encoding="utf8")
        with f:
            # TODO: Test if XML generation via external library e.g. via LXML produces nicer code
            metadata = '''<?xml version="1.0" encoding="UTF-8" ?>
<resource xmlns="http://www.tib.eu/fileadmin/extern/knm/NTM-Metadata-Schema_v_2.2.xsd">
  <alternateIdentifiers>
    <alternateIdentifier alternateIdentifierType="local-frab-event-id">''' + event_id + '''</alternateIdentifier>
  </alternateIdentifiers>
  <titles>
    <title language="''' + lang + '''">''' + (title or '') + '''</title>
    <title titleType="Subtitle" language="''' + lang + '''">''' + (event.find('subtitle').text or '') + '''</title>
</titles>
  <creators>
    ''' + '\n    '.join(['<creator><creatorName>{}</creatorName></creator>'.format(p) for p in persons]) + '''  
  </creators>
  <language>''' + lang + '''</language>
  <genre>Conference</genre>
  <descriptions> 
    <description descriptionType="Abstract" language="''' + lang + '''"><![CDATA[''' + abstract + ''']]></description>
  </descriptions>
  <additionalMaterials>
    ''' + '\n    '.join(['<additionalMaterial additionalMaterialType="{a[0]}" additionalMaterialTitle="{a[1]}" relationType="isSupplementedBy">{a[2]}</additionalMaterial>'.format(a=a) for a in material]) + '''  
    ''' + '\n    '.join(['<additionalMaterial additionalMaterialType="URL" additionalMaterialTitle="{0}" relationType="isSupplementedBy">{1}</additionalMaterial>'.format(
                          a.text, a.attrib['href']) for a in event.find('links')]) + '''  
    <additionalMaterial additionalMaterialType="URL" additionalMaterialTitle="media.ccc.de" relationType="isCitedBy">https://media.ccc.de/v/''' + slug + '''</additionalMaterial>
    <additionalMaterial additionalMaterialType="URL" additionalMaterialTitle="fahrplan.events.ccc.de" relationType="isCitedBy">''' + link + '''</additionalMaterial>
  </additionalMaterials>
  <keywords>
    <keyword language="''' + lang + '''">''' + (event.find('track').text or '') + '''</keyword>
  </keywords>
  <publishers>
    <publisher><publisherName>Chaos Computer Club e.V.</publisherName></publisher>
  </publishers>
  <publicationYear>2017</publicationYear>
</resource>'''
            f.write(metadata)


def find_recoding(guid):
    # request event + recordings from voctoweb aka media.ccc.de
    voctoweb_event = requests.get('https://media.ccc.de/public/events/' + guid).json()

    for r in voctoweb_event['recordings']:
        # select mp4 which contains only the orginal language
        if r['mime_type'] == 'video/mp4' and r['language'] == voctoweb_event['original_language']:
            return r

    return None


import lxml.html
import lxml.html.clean

# from https://stackoverflow.com/a/42461722/521792
def strip_tags(string):
    tree = lxml.html.fromstring(string) 
    clean_tree = lxml.html.clean.clean_html(tree)
    return clean_tree.text_content()


if __name__ == "__main__":
    if dry_run and not os.path.exists('temp'):
        os.mkdir('temp')

    main()


