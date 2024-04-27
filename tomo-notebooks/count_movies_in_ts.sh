#!/bin/bash
# this is to coount number of moviemovie files in each TS.

for i in {1..31}
do
    n=$(printf "%02d" $i)
    #echo "ts-${n}"
    count=$(find ./ -name "TS*ts-${n}*.eer"  | wc -l)
    echo "ts-${n} ${count}"
done
