/* plan9port's strtomp lacks 9front's base-zero, binary and octal parsing. */
static mpint*
constant(char *s)
{
	mpint *n, *radix, *digit;
	int base, d;
	char *start;

	base = 10;
	if(s[0] == '0'){
		if(s[1] == 'x' || s[1] == 'X'){
			base = 16;
			s += 2;
		}else if(s[1] == 'b' || s[1] == 'B'){
			base = 2;
			s += 2;
		}else if(s[1] >= '0' && s[1] <= '7'){
			base = 8;
			s++;
		}
	}
	n = mpnew(0);
	radix = uitomp(base, nil);
	digit = mpnew(0);
	start = s;
	for(; *s; s++){
		d = *s >= '0' && *s <= '9' ? *s-'0' :
		    *s >= 'a' && *s <= 'f' ? *s-'a'+10 :
		    *s >= 'A' && *s <= 'F' ? *s-'A'+10 : base;
		if(d >= base)
			break;
		mpmul(n, radix, n);
		mpadd(n, uitomp(d, digit), n);
	}
	mpfree(radix);
	mpfree(digit);
	if(s == start){
		mpfree(n);
		return nil;
	}
	return n;
}
