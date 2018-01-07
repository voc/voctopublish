#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os, sys
import lxml.etree
import ftputil
import configparser, argparse 
 
cp = configparser.ConfigParser()
cp.read('../client.conf')
config = cp['TIB AV Portal']
 
parser = argparse.ArgumentParser(description='TIB AV Portal: Upload and metadata generation ') 
#parser.add_argument('conference', help='conference slug, e.g. emf16 ') 
parser.add_argument('--upload', action='store_true')
parser.add_argument('--verbose',  '-v', action='store_true', default=False)
args = parser.parse_args() 


#schedule = lxml.etree.parse("https://programm.froscon.de/2017/schedule.xml")
schedule = lxml.etree.parse("temp/schedule.xml")
frab_base_url = 'https://programm.froscon.de/2017' # without trailing slash!

host = ftputil.FTPHost(config['server'], config['user'], config['password']) 

dry_run = not args.upload
#TODO: use argument parser?
ignore_licence = True

def main():
    for event_id in schedule.xpath(u'day/room[starts-with(@name, "HS") or @name="C116 (OSGeo)"]/event/@id'):
        event = schedule.xpath('day/room/event[@id="' + event_id + '"]')[0]
        title = event.find('title').text
        slug = event.find('slug').text.strip()
        #filename = slug + '-hd.mp4'
        filename = event_id + '-hd.mp4'
        file_url = 'http://live.ber.c3voc.de/releases/froscon2017/' + filename 
        link = frab_base_url + '/events/{0}.html\n'.format(event_id)
        local_path = '/srv/releases/froscon2017/' + filename

        if args.verbose:
            print('== ' + title)
        #print(event.find('room').text)


        if not os.path.exists(local_path):
            sys.stderr.write(" \033[91mERROR: " + title + " is not available as mp4 file \033[0m\n")
            continue

        if not ignore_licence and event.find('recording').find('license').text is None:
            sys.stderr.write(" \033[91mERROR: " + title + " has empty recoding license \033[0m\n")
            continue


        if not dry_run:
            if not host.path.exists(slug):
                host.mkdir(slug)
            # TODO?: use callback function to display progress
            host.upload_if_newer(local_path, slug + '/' + slug + '.mp4') 

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

        # not yet in use for froscon
        # future TODO: upload pdf's from frab to ftp host
        material = []
        if os.path.isfile('temp/{}.pdf'.format(slug)):
            material.append(('File', 'Folien als PDF-Datei', '{}.pdf'.format(slug)))
        for a in event.find('attachments'):
            path = a.attrib['href'].split('?')[0]
            basename = os.path.basename(path)
            if os.path.isfile('temp/{}/{}'.format(slug, basename)):
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
            # TODO: Test if XML generaation via external library e.g. via LXML produces nicer code
            metadata = '''<?xml version="1.0" encoding="UTF-8" ?>
<resource xmlns="http://www.tib.eu/fileadmin/extern/knm/NTM-Metadata-Schema_v_2.2.xsd">
  <alternateIdentifiers>
    <alternateIdentifier alternateIdentifierType="local-frab-event-id">''' + event_id + '''</alternateIdentifier>
  </alternateIdentifiers>
  <titles>
    <title language="eng">''' + (title or '') + '''</title> 
    <title titleType="Subtitle" language="eng">''' + (event.find('subtitle').text or '') + '''</title>
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
    <additionalMaterial additionalMaterialType="URL" additionalMaterialTitle="Vortrag auf froscon.de" relationType="isCitedBy">''' + link + '''</additionalMaterial>
  </additionalMaterials>
  <keywords>
    <keyword language="''' + lang + '''">''' + (event.find('track').text or '') + '''</keyword>
  </keywords>
  <publishers>
    <publisher><publisherName>Free and Open Source software Conference (FrOSCon) e.V.</publisherName></publisher>
  </publishers>
  <publicationYear>2017</publicationYear>
</resource>'''
            f.write(metadata)


import lxml.html
import lxml.html.clean

# from https://stackoverflow.com/a/42461722/521792
def strip_tags(string):
    tree = lxml.html.fromstring(string) 
    clean_tree = lxml.html.clean.clean_html(tree)
    return clean_tree.text_content()


if __name__ == "__main__":
    main()

