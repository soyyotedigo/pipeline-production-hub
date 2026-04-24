//Maya ASCII 2024 scene
//Name: anim_v001.ma
//Last modified: portfolio fixture for Pipeline Production Hub
//Codeset: 1252
requires maya "2024";
currentUnit -l centimeter -a degree -t film;
fileInfo "application" "maya";
fileInfo "product" "Maya 2024";
fileInfo "version" "2024";
createNode transform -n "pCube1";
	setAttr ".t" -type "double3" 0 0 0 ;
createNode mesh -n "pCubeShape1" -p "pCube1";
	setAttr -k off ".v";
	setAttr ".vir" yes;
	setAttr ".vif" yes;
createNode polyCube -n "polyCube1";
	setAttr ".cuv" 4;
// End of anim_v001.ma
