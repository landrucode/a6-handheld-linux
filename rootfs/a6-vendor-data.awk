# Decode iw vendor DATA attributes; fail closed on framing/length mismatch.
function hex(s, i,v,c) { v=0; for(i=1;i<=length(s);i++){c=index("0123456789abcdef",substr(s,i,1))-1;if(c<0)exit 1;v=v*16+c} return v }
/^vendor response: / { for(i=3;i<=NF;i++){if(length($i)!=2)exit 1; b[++n]=hex($i)} }
END {
 if(!n)exit 1
 for(o=1;o<=n;){
  if(o+3>n)exit 1
  z=b[o]+256*b[o+1]; k=b[o+2]+256*b[o+3]
  if(z<4 || o+z-1>n)exit 1
  if(k==2)for(j=o+4;j<o+z;j++)data[++d]=b[j]
  o+=int((z+3)/4)*4
 }
 if(o!=n+1 || d!=expected)exit 1
 for(i=1;i<=d;i++)printf "%02x",data[i]
 printf "\n"
}
