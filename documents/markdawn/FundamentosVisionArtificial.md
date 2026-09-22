Fundamentos Visión Artificial <u>felipe.buitrago@ucaldas.edu.co</u> 

**Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas** 



<!-- Start of picture text -->
Imagen de Colombia como un cubo 3x3<br>(alto=3, ancho=3, canales=3 BGR)<br>Columna<br>fe) f Fi Colores en OpenCV (BGR)<br>[amarillo = [0, 255, 255]<br>0 Bau = (255, 0,0]<br>BB Rojo = [0, 0, 255]<br>Cada pixel es un vector BGR<br>iJ<br>m4 (0,8) [0, 255, 255]<br>(1,1) [255, @, @]<br>(2,2) [@, @, 255]<br>2<br>La imagen completa es<br>un cubo (3x3x3)<br>Forma del cubo (imagen):<br>(3, 3, 3) alto<br>¥ + ™ (3)<br>alto | ancho canales<br>ABER)BGR) P canales<br><——— )3<br>ancho (3)<br><!-- End of picture text -->

Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas 



<!-- Start of picture text -->
Representacion BGR en OpenCV - Bandera de Colombia<br>Bandera de Colombia (vista normal) Valores BGR por cada color de la bandera<br>se almacena en orden Color (real) Apariencia Valor en OpenCV (B, G, R)<br>BGR (Azul, Verde, Rojo) ;<br>Amarillo ( O 255., 258 }<br>|B |G [e |<br>Descomposicién de canales en OpenCV (BGR)<br>Canal B (Azul) Canal G (Verde) Canal R (Rojo)<br>a |<br>Valores por fila (B): Valores por fila (G): Valores por fila (R):<br>Amarillo 0 | Azul +255 | Rojo +0 Amarillo 255 | Azul+0 | Rojo +0 Amarillo + 255 | Azul +0 | Rojo > 255<br>Ejemplo [ 0, 255, 255] [0, 255, 255] | [ 255, 0, 0] [255, 0, 0]| [0, 0, 255] r<br>de matriz | (9, 255, 255] [ 0, 255, 255] | [ 255, 0, 0] [ 255, 0, 0]| [0, 0, 255] eves<br>pelueniGpency(3x3 pixeles) [9,0, 255, 7 255 1190, 255, , 255 ] [ 255, , 0, 0, 0 yi 255, , 0, 0, 0 J [ 0, 0, 0, , 255 ] piesG = Verde<br>[ 0, 255, 255] [0, 255, 255] | [ 255, 0, 0] [ 255, 0, 0]) [0, 0, 255] R= Rojo<br><!-- End of picture text -->

Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas 



<!-- Start of picture text -->
1. BANDERA DE COLOMBIA EN RGB 2. BANDERA DE COLOMBIA EN HSV 3. VALORES HSV APROXIMADOS<br>(Representacién visual) (Representacién visual) DE CADA COLOR<br>Color (Real) RGB (0-255) HSV (Opencv)<br>0-179) | (0-255)<br>RGBConveisier> HSV Amarillo | (255, 255,0) | |( 30 255 255<br>=> | en (00,255) (120 255 255<br>-<br>RGB: cada pixel tiene 3 canales (R, G, B) HSV: cada pixel tiene 3 canales (H, S, V)<br>4. FORMULAS DE CONVERSION DE RGB A HSV<br>Sea R, G, B € [0, 1] (valores normalizados) Cmnax Oa=0 0, siCnax = 0 pets: ateae<br>Donde: EeeathGD= Max(R, G, B) 60° oy, x (G-B)“5 mod 6, siCmac=R= | 5 Z a. si Coax #0 S oe€ [0, 255]<br>p=~ Pont255' Gg"255°_ Gove pp ~_ Bavit255 Ryeee a) bic 60°oor xx (2 (2fee  Zs+2), 4). SiGmax=BSi Guay = G | Y= Cmaxaa Ja(El mitad matizWre delH en valor[07255] OpencV eni grados: es<br>| | Hopency =)<br>5. EJEMPLO DE CALCULO PARA LOS COLORES DE LA BANDERA<br>6. RESUMEN VISUAL<br>R=1, G=1, B=0 R=0, G=0, B=1 Ret Ge onewo (Como se ve) (RepresentaciénHSV)<br>Geet, Cape) Amt Cage 1,0, Bet Cmax= 1, Coin= 0, A=1<br>Cmax = R = G Cmax = B Cmax = R<br>Ht = 60° x ED moas = or x1= 60° = 60x (BD 44) = core 044) = 240" HY= OF es a<br>V= Cmax = 1 V= Coax = 1 V= Cmax = 1 En HSY, el color se representa por:<br>HSVHSVen (grados)OpenCv == (30,(60°, 1,255,1) 255) HSVHSVen (grados) Opencv == (120,(240°, 1,255,1) 255) HSVHSVen (grados) OpenCV == (0,(0°, 1,255,1) 255) +sya H-=tipoVe britedelrede de colorcoer (matiz)aaron<br><!-- End of picture text -->

Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas 



<!-- Start of picture text -->
Transformacio6nes de BGR a HSV en OpenCV<br>OpenCV lee las imagenes en formato BGR. Para trabajar con color de forma mas intuitiva,<br>podemos convertirlas al espacio HSV (Tono, Saturacién, Valor).<br>1. Imagen Original (BGR) 2. Imagen en HSV (compuesta) Qué representa HSV?<br>4 i H (Hue / Tono): color puro<br>. (0° a 179° en OpenCv)<br>~ eid a ee —_ S (Saturation/ Saturacién):<br>s FigBh ROESibigt OR Rete ev2.evtColor( intensidad(0 = otis, 255del color= color puro)<br>imagen, V (Value / Valor): brillo<br>cv2:COLoRpenzHsv) (0 = negro, 255 = maximo brillo)<br>= 4<br>————<br>~ a F = + ES<br>» SE at P \<br>3. Canales HSV por separado<br>179° H - Tono (Hue) $ - Saturacién (Saturation) V - Valor (Value)<br>a 255 Sr 255 al> rearséPor quéetausar HSV?ee ce<br>E tras ee icf dia | ~ is Vs menos sensiblea cambios<br>| Ce - cheatsPE rma mis robusta<br>10)ean |tenAis—— ad AONE de iluminacién‘ (valor).<br>ii SSS] es in V Ideal para aplicaciones como<br>i ye detecci6n de objetos por color,<br>- «>a seguimiento, visién robstica, etc.<br>o ° °<br>Representa el tipo de color Indica qué tan “puro” es el color. Indica el brillo de la imagen.<br>(rojos, verdes, azules, etc.) Blanco = color puro, Negro = gris Blanco = muy brillante, Negro = oscuro<br>Cédigo en OpenCv (Python) Rangos en OpenCV (8 bits por canal)<br>import cv2 mp + HE 8-179 equivale a 0° - 360°)<br>imagen_bgr = cv2.imread('paisaje.jpg') # OpenCV carga en BGR © 9S: @- 255 (0 = gris, 255 = color puro)<br>imagen_hsv = cv2.cvtColor(imagen_bgr, cv2.COLOR_BGR2HSV) # Conversidn a HSV + Vi @- 255 (0 = negro, 255 = muy brillante)<br><!-- End of picture text -->

Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas 



<!-- Start of picture text -->
El espacio CIELAB (L*a*b*) esta disefiado para que la distancia entre colores sea<br>perceptualmente uniforme para el ojo humano.<br>1. RGB (Entrada) 2. De RGB a XYZ 3. De XYZ a CIELAB<br>. 1. Normalizar RGB a [0, 1): 1. Normalizar por el blanco de referencia (D65):<br>“955° 9-955’ °~ 255 ee igg  ae<br> - Pe Lag eas ee poe, yo<br>2. Correccién gamma: (Xn = 95.047, Y, = 100.000, Z, = 108.883)<br>eb = si C < 0.04045 = 2. Funcién f(t):<br>R Clin= 4 76 24 1/3 es (&)”<br>(S928) si C > 0.04045 f@)= (2s)<br>G donde C € {r, aBOSG9, b} 3(B)'t+&ae E sits ($)*iy<br>——EEEEES 3. Conversi6n a XYZ (Iluminante D65): 3. Calculo de D*a*b*: Rangos tipicos:—<br>R,vaneG, B € tO.(0, 255] 258) | beY | =| 0.21260.4124 0.71520.3576 0.07220.1805] | [|  ruing,tin L*Y= = 116 f(y) —16= L*5 € [0,100]5<br>ae — J 3 0.0193 0.1192 0.9505 } | din a = 500 [ f(x) — f(y) a* € [-128,127]<br>b* = 200 [ f(y) — f(z)] bt © [-128,127]<br>Resultado: X, Y, Z (Tristimulos del color)<br>Ejemplo de Imagen en RGB Ejemplo de Imagen en CIELAB (Puro) Qué representa cada componente en CIELAB? JE a<br>100<br>psi 0 =negro, 100 = blanco (amarillo)<br>Lae~ "=  L* (Luminosidad) -a’ . 4p?<br>——aeseS7 © a* 2(Componente verdea «> rojo)‘ (verde) a ><br>- Pee negativo: verde | positivo: rojo (0)<br>~~ a?  b* (Componente azul «+ amarillo) -b*<br>“ negativo: azul | positivo: amarillo (azul)<br>0<br>Resumen del flujo: RGB —* (Normalizacin + Gamma) —* XYZ —* (Normalizacién) —> CIELAB (L*a*b*)<br><!-- End of picture text -->

Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas 



<!-- Start of picture text -->
OPERACION AND ENTRE DOS IMAGENES<br>La operacion AND se aplica pixel por pixel.<br>Imagen 1 ] AND { Imagen 2 a Resultado<br>(Paisaje) (Mascara de circulos) = (AND)<br>IMAGEN 1 IMAGEN 2<br>(Paisaje) (Mascara de circulos) RESULTADO (AND)<br>ale OY BG AS as | ees<br>We SSS3 AND = xiii<br>sy er oa,<br>ry Fta A tti" gana wed<br>eS we<br>Ejemplo de pixeles Ejemplo de pixeles (mascara) Ejemplo de resultado<br>R G B R_| G | B | _ pentro det circulo Dentro del circulo: G B<br>120 200 150 255 | 255 | 255 (blanco = 255) Se conserva el pixel 420 200 150<br>Valores reales del paisaje R G B | _ Fuera del circulo Fuera del circulo: R G B<br>(0 - 255) 0 () 0 | (negro = 0) Seeliminael pixel 0 0<br>AND eséComo una operaci6nfunciona?légica: En imagenes: Formula: Aplicaciones:—<br>* 1AND1=1 (se conserva) * Blanco (255) acttia como 1 ———— = ~ + Aplicar mascaras<br>* OAND1=0 (se elimina) (conserva el pixel) Tresuttado(% Y) = 11(x, y) AND I2(x, y) * Extraer regiones de interés<br>* 1ANDO=0 (se elimina) + Negro (0) acta como 0 : ‘+ Segmentacién<br>* OANDO=0 (se elimina) (elimina el pixel) Aplicada a cada canal (R, G y B) * Visién por computadora<br><!-- End of picture text -->

Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas 



<!-- Start of picture text -->
éCOMO FUNCIONA EN OPENCV?<br>Para encontrar las diferencias entre dos imagenes, se usa la RESTA ABSOLUTA (absdiff)<br>y luego se aplica un umbral para resaltar los cambios.<br>@ imagens @ imagen2 © Resta absoluta oO © Diferencias<br>(Original) (Con diferencias) (absdiff) Umbral (threshold) (final)<br>oil te” pte @o i” beeen” n<br>justeoes= - at cP a5 eeraefn—— | : om } } ; | P P Fd ,<br>= 3 *<br>Cédigo en OpenCV (Python) ee -<br>Sinfteeya2 2Qué hace cada paso? Explicacion Tabla de ejemplo (un pixel)<br>import nunpy as np<br>#ingiimg21. Cargar== cv2.imread('imageni.png')cv2.imread(*imagen2.png')imagenes ## ImagenTnagen originalcon diferencias @© cargacigiiesapncanncmsncrins.ia imagen original +‘GieraschLa funcién cv2.absdifori f()Ais calcula ogee la Imagen?a | Imagen2(2) Restaabs_In- 12) | Umbral(630)<br># 2. Asegurar misao tanafo onhe cvacty<br>img? = cv2.resize(ing2, (img1.shape[1], ing1.shape[0])) © Calculate diferenciaabsoluta por pixet i ae 120 120 ° 0 (negro)<br># 3. Resta absoluta zonas igual.<br>Testa = cv2.absdiff(ingi, img2) 1hsy) ~ ROayL 200 50 150 | 255 (blanco)<br>#Sli4. Convertirmeee a escalael de grisesAS ‘+ Los valores altos (blanco) son zonas « 1 0 (negre<br>on. penn) © coniaretninagensescae decries * envio 9 Ofre)<br>#5 qholtear amoral<br>para resale gf erencies cymesu_smwny) _@ Aolca nur par cbr sb<br># Ss Mortran. Cesubtagr las diferencias (blanc= cambi ). o + Elumbral convierteesas diferencias Il 0= sin diferencia (negro)<br>ev2-inshow( "Imagen 1", img) en blancopuroSu  para que seanntlfaciles ‘<br>cv2.imshow('Imagen 2", img2) © Muestra los resultados. Gaver 0 255= diferencia (blanco)<br>ev2inshow(cv2.waitKkey(0)ev2destroyALlwindows ‘Oiferencias',() unbral)<br>Opencv permite detectarciferencias entre dos imagenes usando resta absolutay umbralzacin. « Juegos infantiles « Seguridad y vigllencia<br>‘iP Conelusién Aplicaciones<br>Es la base de muchos juegos “Encuentra las diferencias” y aplicaciones de vision por computadora. *Deteccién de camblos _» Seguimiento de objetos<br><!-- End of picture text -->

Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas 

# Filtros 

**Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas** 



<!-- Start of picture text -->
1. Qué es un filtro en visi6n artificial?<br>Un filtro es una operacién que se aplica a una imagen para modificar sus pixeles con el objetivo de resaltar informacién importante o reducir<br>ruido. En visién artificial, los filtros se usan para mejorar la calidad de la imagen, extraer bordes, detectar patrones, suavizar, realzar detalles,<br>entre otros.<br>La mayoria de los filtros trabajan mediante convolucién, es decir, moviendo una pequefia matriz (kernel) sobre cada pixel de la imagen<br>y calculando un nuevo valor a partir de los pixeles vecinos.<br>2. EQué es el kernel? Vecindad de la imagen Kemet<br>El kernel (o mascara) es una pequefia matriz de ntimeros que define como se combinaran los pixeles es(3x3 ) Gishx: Resultado<br>* Se desplaza por toda la imagen.<br>Ejemplo:* Luego se suman los resultados para obtener el nuevo valor del pixel central. [ 95 | 90 | 2 |<br>Un kernel de 3x3 tiene 9 valores que determinan el comportamiento del filtro. Sums total = 900 =rnuevo: valor del phaal central<br>3. Tres filtros importantes en visién artificial<br>1) Filtro Gaussiano (Suavizado) 2) Filtro de Sobel (Deteccién de bordes) 3) Filtro Laplaciano (Realce de bordes)<br>Reduce el ruido de la imagen y suaviza los cambios bruscos Detecta bordes resaltando los cambios de intensidad en Resalta los bordes y detalles finos. Muy util para identificar<br>de intensidad. horizontal y vertical. contornos.<br>Kernel 3x3: : KernelsSebelenX3x3: (G,) __Sobelen¥(,) Casas:emai: ToTao]<br>eral cal i [afo[a] [-+[-[-]<br>La ]2 [2 | [2{ol2} [ofoto] [ofa fo]<br>[afeta] [+fe{s]<br>Hemp: Ejemplo (bordes en X + Y): Blemplo:<br>Imagen original Con filtro Gaussiano ey Con filtro Sobel Imagen original Con filtro Laplaciano<br><!-- End of picture text -->

Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas 

# Filtro Gaussiano 

**Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas** 



<!-- Start of picture text -->
Before After<br>5i ¢) _-— 2- s | | =pe * :<br>uli) Lu nm er IA 5 \ e a fa<br>& + * .<br>} iJ 4 a<br>f . : 5 ‘. 2% 3<br><!-- End of picture text -->

Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas 



<!-- Start of picture text -->
De imagenes ruidosas ) s ° . e Visién artificial<br>a informacién dtil ra =- | ro Uu Siano - Imagenes mas claras (2)<br>= ? . para mejores decisiones<br>1. Una imagen puede contener ruido 2. El filtrocon combinasus vecinos cada pixel |/ 3, La imagen queda mas suave y estable<br>faspomsaa{ or:rae  ® fe: 00Fait @4 Mg Guerre rha| Seies > Imagen original i Filtro gaussiano _Imagen suavizada<br>oe ae alate . h A an ev |<br>m8. 0% BA Ge om |B oe Be ae<br>i least hod > peed r =i Vecinos: peso : hd ‘ > > - ¥<br>Ee Fone: a o> Ie ee, © ®<br>B ‘< cig 4 eo = ang «. | Nas yess 0a 4 lips<br>i 7A Dy * PF bs zara<br>Vignepan be uh?,) G0)ae oS, | |Todo2 divididoey entre : | 16 {_) Esauinas: menor peso AOSCL eerere)BESS ss Se teriaAyerVo p wsp<br>Sa) i<br>a We erg | Calculo del nuevo valor | | El suavizado facilita tareas posteriores: |<br>1, Cee (1-10 + 2-10 + 1-10,+ |_sil|t 1 | meena | | Go) } Facilita:<br>eeReaA eatsECa(ENa aaNeT EE, | 10 | 10 | 10 | 2:10 +1-10+2-1041-10)/16 4-200 + 2-10 + *siby| \\Ls a1it =2 ti ' ~~"=~?ASOD J!| — |»@ detecinSegmentaciénerde boresoe<br>deEl ruido intensidad produceque pequefiaspueden  variacionesdificultar RE_l valoreR GrdpiaceDUTT AS NuevoNuevo= valor valor == 57.5 920 / 16 mejorPersona definida Automévilmés Claro Sefcos de trénsito=a @ ansisisde: formas<br>el analisis de la imagen. respecto a sus vecinos El valor extremo se reduce al mezclarse A oleate Setanta Oboe Giec<br>% yy, A ‘ prepara la imagen para que otros algoritmos trabajien mejor.<br>\ ) \ con la informacién de los pixeles vecinos. i) a ea )<br>gi | tv. | El filtro gaussiano reduce variaciones pequefias de intensidad G<br>as => Promedi lerado =p] mage! izada tAn ~\ )~ | al reemplazar cada pixel por un promedio ponderado de sus vecinos. |<br>¢ po ! Suey Conclusion ? Esto produce una imagen mas suave y adecuada para etapas | .<br>a<br>posteriores de visién artificial. )<br><!-- End of picture text -->

Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas 

# Algoritmo Canny 

**Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas** 

Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas 



<!-- Start of picture text -->
= e sae =<br>: . - } Deteccion<br>») Algoritmo de Canny: matematicaspasoapaso —{ I scteccis<br>* =<br>ee e: Ejemplo con una imagen 3x3 para entender cémo se detecta un borde ———}} de bordes<br>1. Laimageny el cambio de intensidad | (@| 2. Calculoz  del gradiente.  con Sobel 3. Decision: ges borde o no?<br>.. es [4 [2] 4] Valor de 6 Resultado<br>10 10 200, Ss EEE 7 SiG > 300 borde fuerte<br>[o [2 | La[2 [1J Si100<G<300 | _ borde débil<br>10 10 Calculo de Gx: Calculo de Gy: SiG< 100<br>{| Gx = (-1-10)+ (-2-10) ++ (0-10) (0-10) + (1-20+ (2-2 0 )0) Gy = (-1-10)+ (0-10) + (-2+ (0 -10) + ( -1-200)0-200) Como G = 760, este punto se clasifica<br>10 10 + (-1-10) + (0-10)+ (1-200) + (1-10) + (2-10)<br>| Gx=-10+0+200-20+0+400 Gy=-10-20-200+0+0++ (1-2 0 0) c» como borde fuerte<br>-10+0+ 200 +10 +20+ 200 Salida binaria (valores): Representacién visual:<br>Alay ala izqui d er daec h aay valores valoresclaros. oscuros Gx = 760 Gy =0 lo |<br>El po5 fasipaedd s 200 peerA vertical.Gx mide Aquiel cambio el cambio horizontal horizontal de intensidad. es muy grande Gyy mideel vertical el cambio es nulo.<br><!-- End of picture text -->



<!-- Start of picture text -->
ja presencia de un borde vertical. Magill dal padienne Precsia do gecko FE | o | 255| 0 |<br>intensidad__Unborde cambia aparecebruscamente donde la GG= = V(Gx?+ V(7602 + Gy?) 02) @@=arctan(0/760) = arctan(Gy/Gx) || ygyeso,detectaunbordehaical El algoritmo;  conserva la ubicacién ae  donde el cambio ;<br>| G=760 @ =0° vertica de intensidad es mas fuerte y marca ese lugar como borde.<br>— a _____ \ ==> == = —<br>0 — = — _ YY ——— - —_—_—_—_—_—_—_—__ — a = ><br>| Flujo del algoritmo de Canny: Matrizde entrada = Sobelenxey | =| Magnitudydireccién |=> =| Borde detectado<br>Si — =e — — = ee /<br>awe Conclusion:OF aan El algoritmoEn este ejemplo, de Canny el salto identifica de 10 a bordes 200 produce al medir un matematicamente gradiente alto, por los lo cambios que se ate de intensidadaEsra entreseotcippixeles.<br><!-- End of picture text -->

Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas 

# Operaciones Morfológicas 

**Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas** 





Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas 



<!-- Start of picture text -->
z z<br>Le‘cilatecten acrega DILATACIONi MORFOLOGICAa @S@a=uc1|1| 1 | Elkemel define<br>itnalee aloe bordeaica’ Ejemplo paso a paso con una imagen de 9x9 la formay<br>los objetos (valor 1) alee oe<br>utilizando un kernel. L—}_expansién.<br>CASO 1: CUANDO TODO ES 0<br>1) Posicién inicial del kernel (2) El kernel se mueve a la derecha C3) El kernel se mueve hacia abajo (4) Resultado final: el kernel recorrié<br>(arriba a la izquierda) y continua recorriendo la imagen toda la imagen y no encontré 1<br>o[olo]olololololo (olofolo;alolololo [olololololojo ole o|olololololololo|<br>afoJofo ooo ojo @/ojo[ojo oo) 0 0 00 0000000 0 0/0/0/0 0/0/0|0<br>ofojojojojo ojolo o/ololeldioio ojo ojo le|6/8/8/0 9/9 PICT ea Ec oe ad<br>o/o|oj0;/0\0 0 0lo 0|0,/0/0,0 0, 0\/0\0 [eclouhentoncorbeta | oahe o0/0/0|0|0 olololo|<br>o©0/o/o 00 olojo 0/0/0/0/0 0 0 010 oo fofoJolo oo 0 o/ofolololololojo|<br>Aas rebepats| Pe Cokehohatstatepota] MP tadepetetetetetabe| OP laLahetfolelette iol<br>0 o/ojo|0|0/0 o|0 ofololololo|ololo [ololololojojolojo ololololojolololo<br>ololojojo|o|o ojo 0/o0/0/0/0 0, 0,010 ojo |o/0/0,/0/0 0 0 [o|ojolojojololjojo<br>ololojo,ojo0|0 olo o0/0/0/0,0 010,00 ojo |o|o,0|/0/0 010 0 o|ojolololojojo<br>[o ol|olo o,olololo ololo|o 0 olololo olojolol/ol|e o olo ol|ololojojolojojo<br>‘Como todos los pixeles son 0, Como todos los pixeles son 0, ‘Como todos los pixeles son 0, No se agregan pixeles.<br>el pixel central es 0. el pixel central es 0. el pixel central es 0. La imagen permanece igual.<br>—_—— ——— — ma CASO 2: CUANDO EL KERNEL ENCUENTRA UN 1 — ——— —_—<br>@ Posicién(arriba inicial det kernel © Erkernel semueveyse acerca al1 © Etkernelse coloca sobreel 1 © Resultadodespués de la dilatacion<br>O]0;0]oofeje|o a la0ololololo izquierda)0 0 0 0 0o |0/0|0[ole o]o0/0|0\/o0]j00 0 0 0 o|o000000000(el 1 queda0 o|0\0 en el centro)ojojo o|o0lololololojojo@ 0/0/0/00/0010<br>oo 0/0 0/0 o 010 ofo[eJofo 010 010 ojo oo 0000 O 0 /ololojojojolalo<br>000000000 olojolojo 00 010 oo ofojo oo 0 0/0 |o MMMM o|o|o<br>0/0 0,0 0 Oo ooo 00/0000 000 0/0 olojojojJoio o 00/0 mum o[o|o<br>0 00,0 0,0 ololo 0 0/0/00 0/0 010 0/0 0000010 0 0 00/0 ojo|0 010<br>0/0/00 0/0 ololo 0 0/0/01 0/0,0\0 0/0 0 0/0/0 oloio 0 0/o0/0 o/o|/0\0\0<br>0 o/o/o o|o oo \0 0 0j0|0 0 0/0 0,0 ojo 0 000 00 0 0 0 ojo ojo|0|00<br>El pixel central es 0. El pixel central es 0. El pixel central es 1. El objeto se expande en todas<br>No se agrega ningtin pixel. No se agrega ningun pixel. Se agregan pixeles (dilatacién). las direcciones segtn el kernel.<br>Pixel(fondo)con valor 0 | Pixel(objeto)p con valor 1 Oo Posicién(3x3) del kernel O Pixel. central del kernel Pixelesla dilataciéneeagregados por<br><!-- End of picture text -->

Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas 



<!-- Start of picture text -->
Zz Zz<br>La EROSION MORFOLOGICA =a<br>Faieren erosiénlos ijusitcoedsbordes eliminade los merespixelesobjetos Ejemploi  pasoa paso con una imageni  de 9x9 tla]7 [| 4]a0] formay:direcoisnEl kernel define la<br>Solo el pixel central se 7 | delaerosion.<br>mantiene en 1 si TODOS los CASO 1: CUANDO TODO ES 0<br>aPixalo bajo etikcarnialsori @ Posicisn inicial de! kernel @ Elkernel se mueve ala derecha — @ Elkernel se muevehacia abajo @ Resultado final: el kernel recorrié<br>(arriba a la izquierda) y continda recorriendo la imagen toda la imagen y no encontré 1<br>@0)0]0 000 0\0 0 ofo;o,0]o oo oo 000000 00 00000000<br>ofojojo oo 000 0 ofo[oje|o oo 00000000 ooo 000000<br>oocjooovo 00 o ofc o colo oo oooo00000 000000000<br>ooo 000000 ooo 00000 ooooovo00 8 000000000<br>9.00 000000 mm} 90 0 0 Oo OO mm 6 fo ol ojo oo => 000000000<br>tjolelelololelole o[elolelefelote 0 ofo[e}olo oo tlole[elototojete<br>oooo0o0 0000 ooo 00000 o olo 0 oJo oo ooo00o00000<br>000000000 00000000 ooo000000 oo0000000<br>ooo000 000 00000000 oooo0000 o 00000000<br>000000000 00000000 00000000 000000000<br>Como todos los pixeles son 0, Como todos los pixeles son 0, Como todos los pixeles son 0, No se elimina ningiin pixel porque<br>NO se cumple la condicién. NO se cumple la condicién. NO se cumple la condicién. no hay pixeles con valor 1.<br>CASO 2: CUANDO EL KERNEL ENCUENTRA UN 1<br>@ (arribaPosiciéna lainicializquierda)de! kernet © Erkernel se muevey se acerca al objeto © delEtkernelobjetose(todos colocalos sobre valoresel centroson 1) ©Resuitado después de la erosién<br>ooofoje|oO]o;o]oofo o00 ojooo010 00ojo00 olofo]ojocfelefe]eloleleloo|o0|/0/0/0/0|0\0\000 0 0 c[ofo[t|1|s]folole00ololo0 0ololojo00 oOvo 00000000ooo0o|o|o/ojo000000/0 0108<br>ofole|+itlefeleloThea Ta ead MP Peberedtc[elelelriolejolepata ee = lohedo 0  elaof1[a]1forele Leto0 0 ZCoo 00000Ce0 0<br>elefelsirit{e[elo ofelelaliia{sialo olololritiajolejo ooo0000000<br>ooofelelolai|s{olelo ofelol+}1jelolae oo 00 00000 oo oo 000OO<br>9 0010000 ofel/elol1jelolvjo oo oo 0 tC 00 oo ooo 000 0<br>oo ooo DOO oo 000 Oo oO oo 0000000 oo oc oo 0 OO<br>El pixel central es 0. El pixel central es 0 porque no todos Todos los pixeles bajo el kernel son 1 Solo el pixel central del objeto<br>No se cumple la condicién. los pixeles bajo el kernel son 1. El pixel central es 1. ‘se mantiene en 1.<br>No se cambia nada. No se cambia nada. Se mantiene el 1 y se eliminan los demas. Los bordes se eliminan.<br>Bh conver(fondo) By Pisctcon(objeto)  valor Oo Posicién(3x3) del kernel [1 Piet central del kernel Pixelespor la erosién eliminados<br><!-- End of picture text -->

Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas 

# Detección Figuras Geométricas 

**Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas** 



<!-- Start of picture text -->
(1) IMAGEN ORIGINAL © conversion a cris © saussian Biur © vetecci6n DE BoRDES (5) ENCONTRAR CONTORNOS<br>Se captura el frame Se convierte la imagen Se aplica un suavizado Se aplica Canny para Se buscan los contornos<br>desde la camara, a escala de grises. para reducir el ruido. detectar los bordes. en la imagen de bordes.<br>frame | —_ gris => | gauss = GaussianBlur(gris) | == | bordes = Canny(gauss) | == | contornos = findContours(bordes)<br>=»/i\ —_————s<br>@© “PRoximacioNn Y CLASIFICACION DE POLIGONOS @ diBusaR PoLiconos v RESULTADO FINAL<br>Cada contorno se aproxima a un poligono y se cuenta la cantidad de lados Se dibujan los poligonos detectados, sus vértices y<br>para clasificar (triangulo, cuadrado, pentagono, etc.) se muestra el nombre segin la cantidad de lados.<br>aproximacion = approxPolyDP(contorno) salida = dibujar_poligonos(frame, contornos, ...)<br>lados = len(aproximacion)<br>— CLASIFICACION POR NUMERO DE LADOS |<br>| ° + Tridngulo d SS= =‘Cuadrado (4)<br>———Triangulo (3)<br>4 © -— cuadrado/ Rectingulo a ——<br>lana / j be >+ PentgonoHexagono [SSSjee<br>i, j @ = Hexagor pee |<br>— —— +) > Poligono (n lados) = ‘Hexagono (6) Rectangulo (4)<br>Gy. RESUMEN DEL PROCESO<br>Q: Frame - Gris > Gaussian Blur -» Canny (bordes) > Contornos -> Aproximacién > Clasificacién > Dibujo del resultado<br><!-- End of picture text -->

Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas 



<!-- Start of picture text -->
Convierte los contornos detectados en poligonos con menos vértices para poder clasificar formas.<br>@ IMAGEN BINARIA (BORDES) (2) ENCONTRAR CONTORNOS 3) CONTORNO COMO CONJUNTO 6 SIMPLIFICACION DEL CONTORNO<br>Se parte de una imagen binaria Se detectan los contornos conectados DEPUNTOS Se aplica el algoritmo de Douglas~Peucker<br>donde los bordes de los objetos en la imagen usando findContours(). Cada contorno esta formado por muchos {implementado en approxPolyDP()), que<br>estan definidos (por ejemplo con Canny). Cada contorno es una lista de puntos. puntos que siguen el borde del objeto. elimina puntos innecesarios manteniendo<br>la forma general.<br>/\<br>4\ /) /?<br>/—— /<br>(\__/>\ im ——._f//<br>(5) CONTORNO APROXIMADO 6) CONTAR VERTICES (7) CLASIFICAR LA FORMA (8) USO EN LA DETECCION<br>El resultado es un poligono con menos Se cuenta la cantidad de vértices del Segtin la cantidad de lados, se clasifica Se dibuja el poligomo aproximado sobre<br>vértices que representa al objeto poligono aproximado (numero de lados). el objeto (tridngulo, cuadrado, pentagono, la imagen original para mostrar el<br>original. hexagone, etc.). resultado.<br>© = Trsnguio _fA l=<br>© = Cuadrado/ Rectangulo —4 =<br>© = Pentagono Se =<br>© ~ Hexagono _——  ~S<br>@ — Heptagono SS aS<br>© = octagono S — SS<br>@ = Poligono den tados a ES<br>_yAy__ RESUMEN DEL PROCESO<br>@: Bordes (Canny) —> findContours() -» Contornos (puntos) —> approxPolyDP() -» Poligono aproximado -> Contarlados -> Clasificar forma<br><!-- End of picture text -->

Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas 



<!-- Start of picture text -->
éCOMO FUNCIONA approxPolyDP()?<br>approxPolyDP(contorno, epsilon, cerrado) simplifica un contorno reduciendo la cantidad de vértices<br>mientras mantiene la forma general del objeto.<br>éQUE ES? PARAMETRO CLAVE: epsilon IDEA PRINCIPAL<br>Es el algoritmo de Douglas-Peucker Es la distancia maxima permitida entre un punto del ‘Cénrseti lia pusitne ynportarniaan Cecquinas)<br>adaptado‘ para poligonos.ce Elimina4 puntosHi contornoé original y el segmentobellaque lo reemplaza.: y eliminarmi  los puntos que no cambian‘ la forma<br>intermedios que estén “cerca” de la linea A mayor epsilon —> mas simplificacién (menos vértices). ps ‘<br>que une dos vérticeseaimportantes. a menor epsilon —> menos simplificacién. : (mas vértices). lel contorno mas alld de una tolerancia (epsilon).<br>PASO A PASO DEL ALGORITMO (Douglas-Peucker)<br>@ conTorNo oricinaL © wnir extremos © ostancia MAXIMA @ comparar CON EPSILON @ RePETIR RECURSIVAMENTE<br>‘Tenemos un contorno con: ‘Se toma el primer y ultimo punto Se busca el punto mas alejado Sid > epsilon, ese punto se Se repite el proceso en cada<br>muchos puntos. del contorno y se traza una linea de esa linea y se mide su considera importante y se divide parte hasta que todos los puntos<br>recta entre ellos. distancia perpendicular (d). el contorno en dos partes. estén a una distancia < epsilon.<br>> t= et > Lyi»<br>See s a _-7 d> epsilon<br>RESULTADO: APROXIMACION DEL CONTORNO EFECTO DEL VALOR DE epsilon<br>El resultado es un poligono con menos vértices que representa la forma original. ‘A mayor epsilon, mas vértices se eliminan.<br>fete seat sean(muypetey aydetallado) pene. epsilonsashoe pequeioette epsilonvi  medio (muyepsilony simpliticado) grande<br>lis liegt tut tie ge L<br>v4 EN RESUMEN Sintaxis:<br>“ ” i approxPolyDP(contorno, epsilon, cerrado)<br>‘NY/._ approxPolyDP() reduce la cantidad de puntos de un contorno manteniendo su forma general, escent easdactoak de Veontatens¥ (Hite aavowtics}|<br>conservando las esquinas y eliminando los puntos innecesarios segtin la tolerancia epsilon. b acastiat ceabeentias(acthiel -<br>+ cerrado: True si el contorno esta cerrado, False si esta abierto<br><!-- End of picture text -->

Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas 



<!-- Start of picture text -->
éQUEa HACE cv2.boundingRect:  (aproximacion)?: : 2<br>Devuelve el rectangulo alineado con los ejes (horizontal y vertical) mas pequefio que contiene<br>completamente al contorno o poligono dado.<br>SINTAXIS QUE RETORNA? EJEMPLO<br>X, ys ty t= ev2. boundingRect (aproximacion) Un rectanguloé definido por (x, y, w, h) Si boundingRect devuelve (50, 30, 120, 80):<br>que encierra completamente al contorno.<br>Donde devuelve: 7 (50, 30) yr; s<br>+ x: coordenada X de la esquina superior izquierda ed 1 \ Nw<br>+ y: coordenada Y de la esquina superior izquierda H H ee ~~ Be<br>‘* w: ancho del rectangulo ! i \ J<br>+ hs alto det rectangulo \ H ee<br>Se< w ee> «—__,,,720—_—><br>éCOMO FUNCIONA? (PASO A PASO)<br>@ conrorNo aproximapo @ puscar extreMos © DeFINIR RECTANGULO © vevoweRr (x, y, w, hd<br>Tenemos un contorno aproximado Se encuentran los valores minimo y Con esos extremos se forma el recténgulo x= minX, y = minY, w = maxX - minx,<br>(poligono) obtenido con approxPolyDP. maximolos puntosdedelX e contorno.Y entre todos alineado a losfigejes quetalllos contiene. h= maxYBe- minY.ET acral<br>minY ®(ini, mint) $5,Honi06 9) % 1 4<br>HH H H<br>minX maxX <—, > <-><br>EJEMPLO REAL PARA QUE SIRVE?<br>Contorno aproximado ev2.boundingRect(aproximacion) IN r<br>wae cass aon @ ara obtenera posicén y taro de un objeto detectado /\<br>as a Gey. SF Eee "ES, 190) 948) @ Para dibujar cuadros (bounding boxes) slrededor de formas faa<br>( =» . oo Secu pt asi on<br>\ j \ y Seen cancer mmiedeery | @ Pararecortar (RON ta region que contiene el objeto. oe Ne,<br>Ss Ls Nfme i ee#1) = he146 —+a engalto det recténguloat @ Para calcular relaciones de aspecto, centrar objetos, ete. < \_/ y |<br>ay EN RESUMEN<br>completamente el contorne o poligono dado y devuelve sus coordenadas (x, y) y dimensiones (w, h).<br><!-- End of picture text -->

Felipe Buitrago Carmona – Facultad Inteligencia Artificial e Ingenierías – Universidad de Caldas 

