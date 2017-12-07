#!/usr/bin/env perl

#
# Checks if all thumbnail and poster images listed in the api are available at
# the specified path
#

#
# PREREQUISITES:
#
# apt-get install libjson-perl libjson-xs-perl libwww-perl liblog-log4perl-perl liburi-perl
#

use utf8;
binmode(STDOUT, ":utf8");
binmode(STDERR, ":utf8");
use strict;
use warnings;

use JSON qw(decode_json);
use List::Util qw(min max);
use Log::Log4perl qw(:easy);
use URI::URL;
use LWP::UserAgent;
use Time::HiRes qw (time alarm sleep);


#
# Configuration
#

# media.ccc.de API starting point
my $api_base_url = 'https://api.media.ccc.de/public/';

# Where the thumbnail files of media.ccc.de are located (used for search /
# replace)
my $static_file_base_url = 'https://static.media.ccc.de/media/';

#
# Globals
#

Log::Log4perl->easy_init($INFO);

my $ua = LWP::UserAgent->new;
$ua->agent('check-rebuild-thumb-images');

#
# Functions
#

sub check_if_image_url_exists_in_new {
  my ($event, $url) = @_;
  # Modify the location of temporary thumbnail build ymmv
  $url =~ s#media\.ccc\.de/media/#media.ccc.de/media/_new/#;
  my $response = $ua->head($url);
  DEBUG sprintf('HEAD %s => %d', $url, $response->code);
  if (! $response->is_success() || $response->code == 404) {
    WARN "image '$url' not found for '$event->{title}' ($event->{url})";
  }
}


sub _get_url {
  my ($url) = @_;
  my $response = $ua->get($url);
  if ($response->is_success) {
    return decode_json($response->decoded_content);
  }
  else {
    die "Could not GET '$url': ". $response->status_line;
  }
}

sub get_conference_list {
  return _get_url($api_base_url .'/conferences')->{'conferences'};
}

sub get_conference_details {
  my ($conference) = @_;
  return _get_url($conference->{url});
}

sub get_event_details {
  my ($event) = @_;
  return _get_url($event->{url});
}

sub check_event_path {
  my ($conference, $event) = @_;
  check_if_image_url_exists_in_new($event, $event->{thumb_url});
  check_if_image_url_exists_in_new($event, $event->{poster_url});
}

sub check_images_for_conference {
  my ($conference) = @_;

  my $events = $conference->{'events'};
  for my $event_idx (0 .. (@$events - 1)) {
    my $event = $events->[$event_idx];
    eval {
      my $event_details = get_event_details($event);
      check_event_path($conference, $event_details);

      INFO sprintf('     (%3d of %3d) event: %s (%s) done',
                    $event_idx + 1,
                    scalar(@$events),
                    $event->{title},
                    $event->{url});
      sleep(0.1);
    };
    if ($@) {
      my $error = $@;
      chomp($error);
      ERROR sprintf("failed to check images for '%s' (%s) event '%s' (%s) message '%s'",
                      $conference->{title}, $conference->{url},
                      $event->{title}, $event->{url},
                      $error);
    }
  }
}

#
# main
#

sub main {
  my $conferences = get_conference_list();
  
  INFO sprintf("checking thumbnail and preview images for %d conferences", scalar(@$conferences));
  
  for my $conference_idx (0 .. (@$conferences - 1)) {
    my $conference_details = get_conference_details($conferences->[$conference_idx]);

    INFO sprintf("%3d of %3d: conference '%s' (%s)",
      $conference_idx + 1,
      scalar(@$conferences),
      $conference_details->{title},
      $conference_details->{url});

    check_images_for_conference($conference_details);
  }
  
  INFO "done";
}

main();
