#ifndef __SLEEP_H__
#define __SLEEP_H__
/* 主机侧壳层：usleep 是**被测对象的一部分**（B27 的教训：
 * 「写 0 → 写 1 → usleep → 写 0」这串顺序本身就是判据），
 * 所以这里不真的睡，而是把每一次调用记进轨迹。 */
void host_usleep(unsigned long us);
void host_sleep_s(unsigned long s);
#define usleep(x) host_usleep((unsigned long)(x))
#define sleep(x)  host_sleep_s((unsigned long)(x))
#endif
