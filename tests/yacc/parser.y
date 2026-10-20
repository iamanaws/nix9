%{
#include <u.h>
#include <libc.h>

int yylex(void);
int yyparse(void);
void yyerror(char*);

char *input;
int answer;
%}

%token NUMBER
%left '+'

%%
result: expression { answer = $1; };
expression: NUMBER
  | expression '+' expression { $$ = $1 + $3; };
%%

int
yylex(void)
{
  if(*input >= '0' && *input <= '9'){
    yylval = 0;
    do
      yylval = yylval * 10 + *input++ - '0';
    while(*input >= '0' && *input <= '9');
    return NUMBER;
  }
  if(*input == 0)
    return 0;
  return *input++;
}

void
yyerror(char *message)
{
  fprint(2, "%s\n", message);
}

void
main(int argc, char **argv)
{
  if(argc != 2)
    sysfatal("usage: parser expression");
  input = argv[1];
  if(yyparse() != 0)
    exits("parse");
  print("%d\n", answer);
  exits(nil);
}
