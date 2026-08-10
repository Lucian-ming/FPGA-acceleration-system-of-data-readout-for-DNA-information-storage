// 位平面 + popcount 的暴力滑窗比对基准：与 FPGA srpe_batch 完全相同的算法。
// 用来回答「同样的暴力算法，一个 CPU 核到底能跑多快」，是 docs/07-performance.md 的实测来源。
// 读段长度由 -DRB= 指定（默认 150）；每条读段同时比对正向与反向互补，取分高者。
//
//   python3 tools/bench_align.py                        # 生成 ref.bin / reads.bin
//   gcc -O3 -march=native -DRB=150 -o align tools/align.c
//   ./align ref.bin reads.bin 2048
//
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <time.h>
#define L 40500
#ifndef RB
#define RB 150
#endif
#define NWD ((RB+63)/64)
#define NW ((L+63)/64 + NWD + 1)
static uint64_t rh[NW], rl[NW];
static inline void getwin(const uint64_t*a,int p,uint64_t*o){
    int w=p>>6,s=p&63;
    for(int k=0;k<NWD;k++) o[k]= s?((a[w+k]>>s)|(a[w+k+1]<<(64-s))):a[w+k];
}
static int align(const uint64_t*ah,const uint64_t*al,int*bp){
    uint64_t th[NWD],tl[NWD]; int best=-1,b=0;
    const int rem=RB-64*(NWD-1);
    const uint64_t mlast = (rem==64)?~0ULL:((1ULL<<rem)-1);
    for(int p=0;p<=L-RB;p++){ getwin(rh,p,th); getwin(rl,p,tl); int c=0;
        for(int k=0;k<NWD;k++){ uint64_t m=~(th[k]^ah[k])&~(tl[k]^al[k]);
            if(k==NWD-1) m&=mlast; c+=__builtin_popcountll(m); }
        if(c>best){best=c;b=p;} }
    *bp=b; return best;
}
int main(int c_,char**v){
    FILE*f=fopen(v[1],"rb"); static unsigned char rf[L]; if(fread(rf,1,L,f)!=L)return 1; fclose(f);
    for(int i=0;i<L;i++){ if(rf[i]>>1) rh[i>>6]|=1ULL<<(i&63); if(rf[i]&1) rl[i>>6]|=1ULL<<(i&63); }
    int n=atoi(v[3]); f=fopen(v[2],"rb");
    unsigned char*rd=malloc((size_t)n*RB); if(fread(rd,1,(size_t)n*RB,f)!=(size_t)n*RB)return 1; fclose(f);
    struct timespec t0,t1; clock_gettime(CLOCK_MONOTONIC,&t0); long chk=0;
    for(int i=0;i<n;i++){
        uint64_t ah[NWD],al[NWD],bh[NWD],bl[NWD];
        for(int k=0;k<NWD;k++){ah[k]=al[k]=bh[k]=bl[k]=0;}
        const unsigned char*a=rd+(size_t)i*RB;
        for(int j=0;j<RB;j++){
            if(a[j]>>1) ah[j>>6]|=1ULL<<(j&63); if(a[j]&1) al[j>>6]|=1ULL<<(j&63);
            unsigned char x=a[RB-1-j]^1;
            if(x>>1) bh[j>>6]|=1ULL<<(j&63); if(x&1) bl[j>>6]|=1ULL<<(j&63);
        }
        int p1,p2,s1=align(ah,al,&p1),s2=align(bh,bl,&p2); chk+=(s1>s2?s1:s2);
    }
    clock_gettime(CLOCK_MONOTONIC,&t1);
    double dt=(t1.tv_sec-t0.tv_sec)+(t1.tv_nsec-t0.tv_nsec)/1e9;
    printf("RB=%d  %d 条(双向) %.3f s → %.3f ms/条  平均分 %.1f/%d\n",RB,n,dt,dt*1000/n,(double)chk/n,RB);
    return 0;
}
