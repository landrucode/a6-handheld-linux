/* Bounded diagnostic: make only the browser cgroup reclaim anonymous pages. */
#include <stdlib.h>
#include <stdint.h>
#include <unistd.h>
#include <stdio.h>
int main(void){
 alarm(60);
 volatile uint8_t *memory=malloc(48*1024*1024);
 if(!memory)return 1;
 puts("PRESSURE_FIXTURE_STARTED");fflush(stdout);
 for(;;)for(size_t n=0;n<48*1024*1024;n+=4096)memory[n]++;
}
