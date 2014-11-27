#include "gme.h"
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) 
{
  Music_Emu *emu;
  gme_err_t e = NULL;
  int i;

  int verbose = (strcmp("-v", argv[1]) == 0) ? 1 : 0;

  e = gme_open_file(argv[1 + verbose], &emu, 44100);
  if (e) {
    fprintf(stderr, "could not open file (%s): %s\n", argv[1 + verbose], e);
    return 1;
  }

  if (verbose)
    printf("%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n","filename","totaltracks", "tracknr","system","game","song","author","copyright","comment","dumper","length","intro_length","loop_length");
  int count = gme_track_count(emu);
    gme_info_t *info;
    e = gme_track_info(emu, &info, 0);
    if (e) {
      fprintf(stderr, "could not get track (%d) info for file (%s): %s\n", i, argv[1 + verbose], e); 
      return 1;
    }
    printf("\"%s\",%d,\"%s\",\"%s\",\"%s\",\"%s\",\"%s\",\"%s\",\"%s\",%d,%d,%d\n",argv[1 + verbose],count,info->system,info->game,info->song,info->author,info->copyright,info->comment,info->dumper,info->length,info->intro_length,info->loop_length);
  return 0;
}
