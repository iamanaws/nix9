%{
#include <stdlib.h>
#include "y.tab.h"
extern int yylval;
%}

%%
[0-9]+    { yylval = atoi(yytext); return NUMBER; }
[ \t\n]+  { /* skip whitespace */ }
.         { return yytext[0]; }
%%
