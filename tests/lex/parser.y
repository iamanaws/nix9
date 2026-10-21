%{
#include <stdio.h>
#include <stdlib.h>

int yylex(void);
int yyparse(void);
void yyerror(char*);
int answer;
%}

%token NUMBER
%left '+'

%%
result: expression { answer = $1; };
expression: NUMBER
  | expression '+' expression { $$ = $1 + $3; };
%%

void
yyerror(char *message)
{
  fprintf(stderr, "%s\n", message);
}

int
main(void)
{
  if(yyparse() != 0)
    return 1;
  printf("%d\n", answer);
  return 0;
}
