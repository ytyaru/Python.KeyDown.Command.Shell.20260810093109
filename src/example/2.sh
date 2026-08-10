#!/usr/bin/env bash
set -Ceu
#---------------------------------------------------------------------------
# kd動作確認
#---------------------------------------------------------------------------
Run() {
	THIS="$(realpath "${BASH_SOURCE:-0}")"; HERE="$(dirname "$THIS")"; PARENT="$(dirname "$HERE")"; THIS_NAME="$(basename "$THIS")"; APP_ROOT="$PARENT";
	cd "$HERE"
	local items="A B aaaaaaaaaaaaaaaa bbbbbbbbbbbbbbbb cccccccccccccccccccccccccccccccccccccccccccccc ddddddddddddddddddddddddddd e f g h i j k l m n o p q r s t u v w x y z A B C D E F G H I J K L M N O P Q R S T U V W X Y Z"
	local selected=$(../kd.py $items)
	echo "選択値: ${selected}"
}
Run "$@"
