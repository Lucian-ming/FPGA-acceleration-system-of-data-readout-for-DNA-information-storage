#ifndef __LWIP_ERR_H__
#define __LWIP_ERR_H__
typedef signed char err_t;
#define ERR_OK           0
#define ERR_MEM         (-1)
#define ERR_BUF         (-2)
#define ERR_TIMEOUT     (-3)
#define ERR_VAL         (-6)
#define ERR_WOULDBLOCK  (-7)
#define ERR_ARG        (-14)
#define ERR_ABRT       (-13)
#endif
