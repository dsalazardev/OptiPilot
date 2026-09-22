# K-MEANS 

FELIPE BUITRAGO CARMONA 







## Descripción 





- Agrupación entre elementos que son similares 



<!-- Start of picture text -->
a L O¢<br>LyLe Lyf+H Z, of CL<br>2Yx 3 ébj om o® fo<br>|<br>x ET | ogGRO Do ®<br>“| he — o@oanane ge<br>ars x Li os 4 Z °<br>=|<br>Vii yy yy o<br>= YZ Uj °° Cluster 1 +<br>2 iy y ° Cluster2 %&<br>BMLLL Cluster 3 OQ<br><!-- End of picture text -->

- Se puede utilizar en datos no etiquetados 

- Algoritmo de aprendizaje automático no supervisado 



## Descripción 





<!-- Start of picture text -->
U/. k-Means Clusters ]<br>a +<br>a 7 °o<br>L / fe}<br>aa LY yy ®<br>LyFa yyy+ o je) o<br>1s x fe ° & oe —y<br>is| x EDeeZt 26 Rae Po oy®<br>ts x Z, Yy Fg oO<br>//jpyZe Vy x Fy fa}<br>Lif yy Yj - Cluster 1 +<br>Lis vi, y fa} Cluster2 %<br>ELT Cluster3 ©<br><!-- End of picture text -->

- Centroide: Elemento central en el espacio n- dimensional de los n Atributos del Data Set. 

- Clúster: Consisten en valores similares. La similitud entre los valores se basa en una medida de distancia entre ellos. 

- Observación: Elemento del grupo de datos 



## Consideraciones 





- Minimizar variación intra-clouster 



<!-- Start of picture text -->
ti “<br>a L O¢<br>LyLe Lyf+H Z, of CL<br>2Yx 3 ébj om o® fo<br>|<br>x ET | ogGRO Do ®<br>“| he — o@oanane ge<br>ars x Li os 4 Z °<br>=|<br>Vii yy yy o<br>= YZ Uj °° Cluster 1 +<br>2 iy y ° Cluster2 %&<br>BMLLL Cluster 3 OQ<br><!-- End of picture text -->

- Maximizar variación extraclouster 



<!-- Start of picture text -->
Distancia<br>• Yi k-Means Clusters ]<br>y d(x;,x;) ZLi | yip ik Yj Kin) i,2 Y+ ° y<br>Ly ‘yy<br>Formula 1 ///Lf a# + g ofom Ks °<br>s x ae y °% $5089 ye. °<br>* | | | oR ese 9 °<br>p= Numero de dimensiones a1" 9 os Qe<br>* x= observaciones evaluados = y * 8 of |<br>Zi yf yj fol Cluster2 %<br>YI LMT Cluster3 O<br><!-- End of picture text -->

## Algoritmo 





Paso 1. k= Número de clousters 

Paso 2. Elección de centroides 

Paso 3. Medir la distancia de las observaciones a los k centroides. (Fórmula 1) Paso 4.Asignar cada observación al centroide mas cercano Paso 5. Por cada grupo, actualizar el centroide, calculando el dato medio del conjunto 

Paso 6. Repetir el paso 3,4 y 5 hasta que no cambien los centroides 

Algoritmo Paso 1. **k= 3** 10 2 12 6 4 8 13 1 10 3 13 1 6 5 13 2 11 AAA <mark>></mark> Aridae:7) 



Algoritmo Paso 2. Elección de centroides 2 1 3 10 12 6 8 13 4 <mark>=_</mark> 1 6 5 13 2 11 10 13 An 





## Algoritmo 

### Paso 3. Medir la distancia de las observaciones a los k centroides. (Fórmula 1) 



<!-- Start of picture text -->
2 1<br>3<br>8 -           = 5 3 8 -           = 6 2 8 -           = 7 1<br>10 12 6<br>13<br>4<br>1 6 5 13 2 11<br>10 13<br><!-- End of picture text -->



## Algoritmo 

### Paso 3. Medir la distancia de las observaciones a los k centroides. (Fórmula 1) 



<!-- Start of picture text -->
2 1<br>3<br>8 -           = 5 3 8 -           = 6 2 8 -           = 7 1<br>10 12 6<br>13<br>4<br>1 6 5 13 2 11<br>10 13<br><!-- End of picture text -->

Algoritmo Paso 4.Asignar cada observación al centroide mas cercano 2 1 3 8 10 12 6 13 4 1 6 5 13 2 11 10 13 A oA <mark>=</mark> ann4 











Repetir Proceso Por Cada Elemento 



## Algoritmo 

### Paso 3. Medir la distancia de las observaciones a los k centroides. (Fórmula 1) 



<!-- Start of picture text -->
2 1<br>3<br>4 -           = 1 3 4 -           = 2 2 4 -           = 3 1<br>10 12 6<br>13<br>1 6 5 13 2 11<br>10 13<br><!-- End of picture text -->

Algoritmo Paso 4.Asignar cada observación al centroide mas cercano 2 1 3 8 4 am] 10 12 6 13 4 1 6 5 13 2 11 10 13 V4 VAA V 







Finalmente 

## Algoritmo 

### Paso 4.Asignar cada observación al centroide mas cercano 







<!-- Start of picture text -->
2 1<br>3<br>;<br>2 1<br>8 11 13 10<br>IAA<br>13 5 4 12<br>CALI)<br>6 6<br>13 10<br>44<br><!-- End of picture text -->







Paso 5 



<!-- Start of picture text -->
Algoritmo<br>Paso 5. Por cada grupo, actualizar el centroide, calculando el dato medio del  |<br>conjunto<br>2 1<br>3<br>;<br>2 1<br>8 11 13 10<br>IAA<br>13 5 4 12<br>CALI)<br>6 6<br>13 10<br>44<br><!-- End of picture text -->



## Algoritmo 

Paso 5. Por cada grupo, actualizar el centroide, calculando el dato medio del conjunto 



<!-- Start of picture text -->
3<br>8 11 13 10<br>13 5 4 12<br>6 6<br>13 10<br><!-- End of picture text -->

8+11+13+10+13+5+4+12+6+ 6+13+10+3=114 

114/13=8.7 



<!-- Start of picture text -->
8<br><!-- End of picture text -->



<!-- Start of picture text -->
Algoritmo<br>Paso 6. Repetir el paso 3,4 y 5 hasta que no cambien los centroides<br>2 1<br>8<br>4<br>2 3 4 1<br>13 11 13 10<br>13<br>12 10<br>5<br>6 6<br>44<br><!-- End of picture text -->



<!-- Start of picture text -->
Algoritmo<br>Paso 6. Repetir el paso 3,4 y 5 hasta que no cambien los centroides<br>3<br>10 1<br>2 2 4 1<br>13 11 13 8<br>a7<br>13<br>12 10<br>5 6 6<br><!-- End of picture text -->



<!-- Start of picture text -->
Algoritmo<br>Paso 6. Repetir el paso 3,4 y 5 hasta que no cambien los centroides<br>4<br>11 1<br>13 8 2 2 3 1<br>13<br>A a<br>13<br>12 10 10<br>5 6 6<br><!-- End of picture text -->



<!-- Start of picture text -->
Algoritmo<br>Paso 6. Repetir el paso 3,4 y 5 hasta que no cambien los centroides<br>6<br>11 2<br>13 6 4 5 1 1 2<br>13 10<br>n<br>AID<br>13<br>12<br>10 8 3<br><!-- End of picture text -->

## Referencias 







<u>https://docs.rapidminer.com/latest/studio/operators/modeling/seg</u> ~~<u>mentation/k</u>~~ <u>_</u> ~~<u>means.html</u>~~ <u>https://www.youtube.com/watch?v=zHbxbb2ye3E</u> 

## Descripción (P) 





<!-- Start of picture text -->
¥<br>ep<br><!-- End of picture text -->

- Centroide 

- Clúster 





- Calcular los centroides de los clústeres promediando todos los valores de un clúster. Los pasos anteriores se repiten para los nuevos centroides hasta que los centroides ya no se muevan o se alcancen los _pasos de optimización máximos_ 

- Ejemplo K=3 



<!-- Start of picture text -->
Vv<br>2 4 6<br>|<br>a<br><!-- End of picture text -->



<!-- Start of picture text -->
Descripción (P)<br>• Centroide<br>• Clúster<br>• Calcular los centroides de los clústeres promediando todos los valores de un<br>clúster. Los pasos anteriores se repiten para los nuevos centroides hasta que los<br>centroides ya no se muevan o se alcancen los  pasos de optimización máximos<br>• Ejemplo K=3<br>3 7 11<br>2 4 6 8 10 12<br><!-- End of picture text -->

## Descripción (P) 







- Centroide 

- Clúster 

- Calcular los centroides de los clústeres promediando todos los valores de un clúster. Los pasos anteriores se repiten para los nuevos centroides hasta que los centroides ya no se muevan o se alcancen los _pasos de optimización máximos_ 

- Ejemplo K=3 



<!-- Start of picture text -->
10 16<br>4<br>2 4 6 8 10 12 14 16 18<br><!-- End of picture text -->

Algoritmo Paso 1. **k= 3** 6 2 10 11 8 13 3 1 1 HO or 4 2 6 5 10 13 13 12 nA 4762 O 

