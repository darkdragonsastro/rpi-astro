/* The standalone Linux loader only needs the format annotation from config.h. */
#define PRINTF_FORMAT(a, b) __attribute__((format(printf, a, b)))
