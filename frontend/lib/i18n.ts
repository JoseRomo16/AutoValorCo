/**
 * Every string the site renders, in both languages, in one place.
 *
 * The shape is `{ es, en }` per string rather than two parallel dictionaries keyed by id.
 * Parallel dictionaries drift: a key gets added to one and not the other, and the only
 * symptom is a missing word in the language nobody was looking at. Here a string that is
 * not translated does not compile.
 *
 * Spanish is the default because the product is Colombian; English exists because the
 * repository is a portfolio piece read by people who do not speak Spanish.
 */

export type Lang = "es" | "en";

export const LANGS: Lang[] = ["es", "en"];

export type Localized = { es: string; en: string };

export const copy = {
  site: {
    name: { es: "AutoValor CO", en: "AutoValor CO" },
    tagline: {
      es: "Cuánto vale un carro o una moto usada en Colombia",
      en: "What a used car or motorcycle is worth in Colombia",
    },
  },
  nav: {
    value: { es: "Valorar", en: "Value" },
    market: { es: "Mercado", en: "Market" },
    method: { es: "Metodología", en: "Methodology" },
    skip: { es: "Saltar al contenido", en: "Skip to content" },
  },
  lang: {
    label: { es: "Idioma", en: "Language" },
    es: { es: "Español", en: "Spanish" },
    en: { es: "Inglés", en: "English" },
  },
  footer: {
    disclaimer: {
      es: "Las estimaciones son informativas y no constituyen un avalúo comercial. Salen de precios pedidos en anuncios, no de precios de venta.",
      en: "Estimates are informational and are not a commercial appraisal. They come from asking prices in listings, not from transaction prices.",
    },
    repo: { es: "Código en GitHub", en: "Source on GitHub" },
    api: { es: "API y documentación", en: "API and docs" },
  },
  coldStart: {
    title: { es: "La primera consulta puede tardar ~1 minuto", en: "The first request can take ~1 minute" },
    body: {
      es: "La API corre en el plan gratuito de Render: se duerme tras 15 minutos sin tráfico y la primera petición espera a que arranque y cargue los dos modelos. Las siguientes responden en milisegundos.",
      en: "The API runs on Render's free plan: it sleeps after 15 minutes without traffic, and the first request waits for it to boot and load both models. The rest answer in milliseconds.",
    },
  },
  form: {
    heading: { es: "Valorar un vehículo", en: "Value a vehicle" },
    intro: {
      es: "Las listas salen del modelo que está sirviendo: solo ofrece marcas, modelos y departamentos con los que de verdad se entrenó.",
      en: "The lists come from the model that is serving: it only offers makes, models and departments it was actually trained on.",
    },
    vehicleType: { es: "Tipo", en: "Type" },
    car: { es: "Carro", en: "Car" },
    motorcycle: { es: "Moto", en: "Motorcycle" },
    brand: { es: "Marca", en: "Make" },
    model: { es: "Modelo", en: "Model" },
    modelAny: { es: "No lo sé / no aparece", en: "I don't know / not listed" },
    modelShowAll: {
      es: "Ver también los modelos con pocos anuncios",
      en: "Show the models with few listings too",
    },
    year: { es: "Año del modelo", en: "Model year" },
    mileage: { es: "Kilometraje", en: "Mileage" },
    department: { es: "Departamento", en: "Department" },
    engine: { es: "Cilindrada (cc)", en: "Displacement (cc)" },
    engineOptional: {
      es: "Opcional. Si no la sabes, déjalo vacío: el modelo trata el dato faltante como señal, no como un promedio.",
      en: "Optional. Leave it empty if you don't know: the model treats a missing value as a signal, not as an average.",
    },
    askingPrice: { es: "Precio pedido (opcional)", en: "Asking price (optional)" },
    askingPriceHint: {
      es: "Si lo pones, se compara contra el rango estimado.",
      en: "If you enter it, it is compared against the estimated range.",
    },
    submit: { es: "Calcular el precio", en: "Estimate the price" },
    submitting: { es: "Calculando…", en: "Estimating…" },
    loadingCatalog: { es: "Cargando las listas del modelo…", en: "Loading the model's lists…" },
    listings: { es: "anuncios", en: "listings" },
    required: { es: "Completa los campos obligatorios.", en: "Fill in the required fields." },
  },
  result: {
    heading: { es: "Precio estimado", en: "Estimated price" },
    range: { es: "Rango P10–P90", en: "P10–P90 range" },
    rangeHelp: {
      es: "Ocho de cada diez anuncios comparables se piden dentro de este rango.",
      en: "Eight in ten comparable listings are asked within this range.",
    },
    asking: { es: "Precio pedido", en: "Asking price" },
    vsEstimate: { es: "frente al estimado", en: "vs the estimate" },
    bargain: { es: "Ganga", en: "Bargain" },
    fair: { es: "Justo", en: "Fair" },
    expensive: { es: "Caro", en: "Expensive" },
    bargainWhy: {
      es: "El precio pedido está por debajo del P10 de vehículos comparables.",
      en: "The asking price sits below the P10 of comparable vehicles.",
    },
    fairWhy: {
      es: "El precio pedido cae dentro del rango de vehículos comparables.",
      en: "The asking price falls inside the range of comparable vehicles.",
    },
    expensiveWhy: {
      es: "El precio pedido está por encima del P90 de vehículos comparables.",
      en: "The asking price sits above the P90 of comparable vehicles.",
    },
    noLabel: { es: "Sin etiqueta para esta vertical", en: "No label for this vertical" },
    noLabelWhy: {
      es: "Solo precio estimado y rango: la banda de esta vertical no es lo bastante precisa para decir si un anuncio es una ganga o está caro. Mostrarla igual sería una afirmación que la medición no sostiene.",
      en: "Estimate and range only: this vertical's band is not precise enough to call a listing a bargain or expensive. Showing the label anyway would be a claim the measurement does not support.",
    },
    noLabelMeasured: { es: "Medición del modelo servido", en: "As measured by the served model" },
    factors: { es: "Qué mueve este precio", en: "What moves this price" },
    factorsHelp: {
      es: "Cada factor multiplica el precio base del modelo. Son exactos, no aproximados: el precio base por el producto de todos los factores da el estimado.",
      en: "Each factor multiplies the model's base price. They are exact, not approximate: the base price times the product of every factor is the estimate.",
    },
    raises: { es: "sube", en: "raises" },
    lowers: { es: "baja", en: "lowers" },
    basePrice: { es: "Precio base del modelo", en: "Model base price" },
    modelVersion: { es: "Modelo", en: "Model" },
    error: { es: "No se pudo consultar la API", en: "Could not reach the API" },
    errorOutdated: {
      es: "La API desplegada es anterior a este sitio: todavía no tiene /catalog. Se arregla sola cuando Render termine de desplegar el último commit.",
      en: "The deployed API is older than this site: it does not serve /catalog yet. This fixes itself once Render finishes deploying the latest commit.",
    },
    errorOffline: {
      es: "Si acabas de abrir la página, lo más probable es que el servicio siga arrancando: espera unos segundos y reintenta.",
      en: "If you have just opened the page, the service is most likely still booting: wait a few seconds and retry.",
    },
    retry: { es: "Reintentar", en: "Retry" },
  },
  market: {
    heading: { es: "Qué dice el mercado", en: "What the market says" },
    intro: {
      es: "Estos números salen de una regresión hedónica con errores robustos (HC3), no del ensamble que estima precios: un ensamble predice bien y no dice cuánto vale un año. Cada barra lleva su intervalo de confianza al 95 %, y lo que cruza el cero se marca como no distinguible de cero.",
      en: "These come from a hedonic regression with robust (HC3) errors, not from the ensemble that estimates prices: an ensemble predicts well and says nothing about what a year is worth. Every bar carries its 95 % confidence interval, and anything crossing zero is marked as indistinguishable from zero.",
    },
    measuredOn: { es: "Medido sobre", en: "Measured on" },
    rows: { es: "anuncios", en: "listings" },
    generated: { es: "Generado el", en: "Generated on" },
    notSignificant: { es: "no distinguible de cero", en: "indistinguishable from zero" },
    reference: { es: "referencia", en: "reference" },
    depreciation: {
      title: { es: "Depreciación anual por marca", en: "Annual depreciation by make" },
      help: {
        es: "Cuánto pierde de valor un vehículo por cada año que cumple, con el kilometraje de un año típico de esa marca ya incluido.",
        en: "How much a vehicle loses per year of age, with a typical year's mileage for that make already included.",
      },
      readingCar: {
        es: "Lectura económica: en carros la teoría popular se sostiene. Las japonesas y coreanas aguantan —Toyota, Mazda, Kia entre 5 % y 6 % al año— y las premium alemanas y Ford caen al doble de velocidad, alrededor del 9 %. Sobre un carro de 90 millones, esa diferencia son ~3,5 millones al año.",
        en: "Economic reading: for cars the folk theory holds. Japanese and Korean makes hold value — Toyota, Mazda and Kia between 5 % and 6 % a year — while the German premium brands and Ford fall twice as fast, around 9 %. On a 90-million-peso car that gap is ~3.5 million a year.",
      },
      readingMoto: {
        es: "Lectura económica, y es el hallazgo del proyecto: una Yamaha pierde 0,9 % al año y su intervalo incluye el cero, es decir que estos datos no la distinguen de no perder nada. Una Bajaj pierde 6,5 %. Comprar moto usada es, en la práctica, pagar casi el precio de nueva en las marcas que aguantan.",
        en: "Economic reading, and the project's headline finding: a Yamaha loses 0.9 % a year and its interval includes zero — this data cannot tell it apart from losing nothing. A Bajaj loses 6.5 %. Buying a used motorcycle means, in practice, paying nearly the new price for the makes that hold value.",
      },
    },
    retained: {
      title: { es: "Valor retenido con la edad", en: "Value retained with age" },
      help: {
        es: "La misma estimación vista como curva: qué porcentaje del valor inicial queda a cada edad.",
        en: "The same estimate as a curve: what share of the initial value is left at each age.",
      },
      reading: {
        es: "Lectura económica: las curvas de las motos son casi planas y las de los carros no. A los diez años un carro ronda la mitad de su valor y una moto de las marcas que aguantan sigue cerca del 90 %. Eso cambia la decisión: en carros conviene comprar usado y en motos la diferencia frente a nuevo es pequeña.",
        en: "Economic reading: the motorcycle curves are nearly flat and the car curves are not. At ten years a car is near half its value, while a motorcycle from the makes that hold value is still close to 90 %. That changes the decision: for cars buying used pays off, for motorcycles the gap against new is small.",
      },
      age: { es: "Edad (años)", en: "Age (years)" },
      retainedPct: { es: "Valor retenido", en: "Value retained" },
    },
    mileage: {
      title: { es: "Cuánto cuestan 10.000 km", en: "What 10,000 km cost" },
      help: {
        es: "Efecto de 10.000 km más en el odómetro, evaluado en la mediana de precio de cada segmento. Los segmentos se cortan por la clase de precio del vehículo (su marca y modelo), no por el precio del anuncio.",
        en: "The effect of 10,000 more kilometres, evaluated at each segment's median price. Segments are cut by the vehicle's price class (its make and model), not by the listing's own price.",
      },
      reading: {
        es: "Lectura económica: el kilometraje se cobra en proporción al valor del vehículo, no en pesos fijos. En el carro mediano 10.000 km valen ~216.000 pesos; en el cuartil más caro, ~323.000. Y en las motos más baratas no se cobra: el efecto no se distingue de cero, así que un kilometraje alto no es palanca de negociación ahí.",
        en: "Economic reading: mileage is charged in proportion to the vehicle's value, not in fixed pesos. On the median car 10,000 km are worth ~216,000 pesos; in the dearest quartile, ~323,000. On the cheapest motorcycles it is not charged at all — the effect is indistinguishable from zero, so high mileage is no bargaining lever there.",
      },
      segmentAll: { es: "toda la vertical", en: "whole vertical" },
      quartile: { es: "Cuartil", en: "Quartile" },
      medianPrice: { es: "mediana", en: "median" },
    },
    regional: {
      title: { es: "Dónde está más caro el mismo vehículo", en: "Where the same vehicle costs more" },
      help: {
        es: "Diferencia frente a Bogotá D.C. para un vehículo comparable: mismo modelo, misma edad, mismo kilometraje, misma cilindrada.",
        en: "Difference against Bogotá D.C. for a comparable vehicle: same model, same age, same mileage, same displacement.",
      },
      readingCar: {
        es: "Lectura económica: en carros el país es casi un solo mercado. Entre el departamento más caro y el más barato hay 8,6 puntos, que en un carro de 90 millones son ~7,7 millones: suficiente para que valga la pena mirar afuera, no para mudarse a comprar.",
        en: "Economic reading: for cars the country is almost a single market. The spread between the dearest and cheapest department is 8.6 points, which on a 90-million-peso car is ~7.7 million: enough to be worth looking elsewhere, not enough to travel for.",
      },
      readingMoto: {
        es: "Lectura económica: en motos el rango es de 60 puntos. La misma moto se pide 28 % más cara en Antioquia que en Bogotá y 31 % más barata en Quindío. Ahí el arbitraje regional sí es real, con una advertencia: el departamento dice dónde se publica el anuncio, que se parece a pero no es dónde está el mercado.",
        en: "Economic reading: for motorcycles the spread is 60 points. The same motorcycle is asked 28 % dearer in Antioquia than in Bogotá and 31 % cheaper in Quindío. Regional arbitrage is real there, with one caveat: the department says where the listing was published, which resembles but is not where the market is.",
      },
    },
    catalogue: {
      title: { es: "Por qué las motos son el caso difícil", en: "Why motorcycles are the hard case" },
      help: {
        es: "Reparto de la importancia del modelo entre identidad (marca, modelo, cilindrada) y estado (edad, kilometraje).",
        en: "How the model's importance splits between identity (make, model, displacement) and condition (age, mileage).",
      },
      identity: { es: "Identidad", en: "Identity" },
      condition: { es: "Estado", en: "Condition" },
      other: { es: "Otros", en: "Other" },
      reading: {
        es: "Lectura económica: el modelo de motos funciona como un catálogo —pesa 4,8 veces más en identidad que en estado—, y el hedónico lo confirma por otra vía: la edad casi no mueve el precio de una moto. No es una limitación del modelo, es un hecho del mercado, y es la razón por la que en motos publicamos precio y rango pero no etiqueta.",
        en: "Economic reading: the motorcycle model behaves like a catalogue — it leans 4.8 times more on identity than on condition — and the hedonic regression confirms it independently: age barely moves a motorcycle's price. That is a fact about the market rather than a limitation of the model, and it is why motorcycles ship a price and a range but no label.",
      },
    },
  },
  method: {
    heading: { es: "Cómo se calcula", en: "How this is computed" },
    intro: {
      es: "De dónde salen los datos, qué modelo contesta, cuánto se equivoca medido fuera de muestra, por qué en motos no hay etiqueta y qué cosas este proyecto no sabe. Las cifras de esta página las reporta el propio modelo servido.",
      en: "Where the data comes from, which model answers, how wrong it is measured out of sample, why motorcycles carry no label, and what this project does not know. The figures on this page are reported by the served model itself.",
    },
    data: { es: "Los datos", en: "The data" },
    dataBody: {
      es: "Anuncios públicos de TuCarro capturados con un cliente que respeta robots.txt, pausa entre peticiones y se identifica. No se guarda ningún dato personal de vendedores (Ley 1581 de 2012). La capa cruda es inmutable y cada captura queda publicada en la rama `data` del repositorio, así que cualquier cifra se puede rehacer desde cero.",
      en: "Public TuCarro listings captured by a client that respects robots.txt, pauses between requests and identifies itself. No personal seller data is ever stored (Colombian law 1581 of 2012). The raw layer is immutable and every capture is published to the repository's `data` branch, so any figure can be rebuilt from scratch.",
    },
    dataCaveat: {
      es: "Son precios pedidos, no precios de venta. Un mercado donde se regatea deja los pedidos por encima de lo que se paga, y esa brecha no está medida aquí.",
      en: "These are asking prices, not transaction prices. In a market where people haggle, asking prices sit above what is paid, and that gap is not measured here.",
    },
    models: { es: "Los modelos", en: "The models" },
    modelsBody: {
      es: "Dos modelos por vertical, porque un sedán y una moto de 125 cc no comparten curva de precios. El objetivo es log(precio). La línea base es una regresión hedónica OLS que cualquier ensamble tiene que superar; el modelo servido es LightGBM, que la supera por 3,8 puntos de MAPE en carros y 21 en motos — casi todo gracias a tratar las categorías crudas en vez de agruparlas antes de un one-hot.",
      en: "Two models per vertical, because a sedan and a 125 cc motorcycle share no price curve. The target is log(price). The baseline is a hedonic OLS regression any ensemble has to beat; the served model is LightGBM, which beats it by 3.8 MAPE points on cars and 21 on motorcycles — nearly all of it from handling raw categories instead of grouping them before a one-hot.",
    },
    bandBody: {
      es: "El rango P10–P90 viene de tres modelos cuantílicos conformalizados. Sin ese paso la banda cubría 67 % y 63 % contra un nominal de 80 %: los árboles pegan los cuantiles al entrenamiento y la banda sale angosta en filas nuevas. Una banda anunciada al 80 % que sostiene 63 % es peor que no tener banda.",
      en: "The P10–P90 range comes from three conformalized quantile models. Without that step the band covered 67 % and 63 % against a nominal 80 %: the trees fit the training quantiles tightly and the band comes out too narrow on unseen rows. A band advertised as 80 % that holds 63 % is worse than no band at all.",
    },
    metrics: { es: "Métricas fuera de muestra", en: "Out-of-sample metrics" },
    metricsBody: {
      es: "Medidas sobre un holdout del 20 % que ningún modelo vio al ajustarse ni al afinarse, y con los grupos de reposteo movidos completos: el mismo vehículo reaparece con otro identificador, y partir por filas dejaba gemelos a ambos lados y halagaba el resultado. Estas cifras las reporta el propio modelo servido en /model-info.",
      en: "Measured on a 20 % holdout no model saw while fitting or tuning, with repost groups moved whole: the same vehicle reappears under a new id, and splitting by row left twins on both sides and flattered the result. These figures are reported by the served model itself at /model-info.",
    },
    vertical: { es: "Vertical", en: "Vertical" },
    mape: { es: "MAPE", en: "MAPE" },
    coverage: { es: "Cobertura de la banda", en: "Band coverage" },
    width: { es: "Ancho medio", en: "Mean width" },
    label: { es: "Etiqueta", en: "Label" },
    trainedOn: { es: "Filas", en: "Rows" },
    published: { es: "se publica", en: "published" },
    withheld: { es: "se retiene", en: "withheld" },
    rule: { es: "La regla de la etiqueta", en: "The label rule" },
    ruleBody: {
      es: "La etiqueta ganga/justo/caro solo se muestra si la banda medida en el holdout cumple dos cosas: cobertura entre 78 % y 82 %, y ancho medio de 60 % del estimado o menos. La ventana de cobertura es de dos lados a propósito. Cubrir de menos dispara «ganga» en anuncios normales; cubrir de más mete en «justo» anuncios que de verdad están mal preciados, y la etiqueta deja de discriminar.",
      en: "The bargain/fair/expensive label only appears if the band measured on the holdout meets two conditions: coverage between 78 % and 82 %, and a mean width of 60 % of the estimate or less. The coverage window is two-sided on purpose. Under-covering fires “bargain” on ordinary listings; over-covering absorbs genuinely mispriced listings into “fair”, and the label stops discriminating.",
    },
    ruleCode: {
      es: "La regla es código con pruebas, no un criterio escrito en un documento: la decisión se toma al exportar el modelo y viaja dentro del artefacto, así que la API no la vuelve a calcular. Cuando la banda de motos se angoste, la etiqueta se enciende sola.",
      en: "The rule is tested code, not a criterion written in a document: the decision is taken when the model is exported and travels inside the artifact, so the API never re-derives it. When the motorcycle band tightens, the label turns itself on.",
    },
    limits: { es: "Limitaciones honestas", en: "Honest limitations" },
    limitsList: {
      source: {
        es: "Una sola fuente. Todo sale de TuCarro, así que lo que se describe es ese mercado y no el país entero.",
        en: "A single source. Everything comes from TuCarro, so what is described is that marketplace rather than the whole country.",
      },
      asking: {
        es: "Precios pedidos, no de venta. El estimado responde «por cuánto se publica esto», que no es «por cuánto se vende».",
        en: "Asking prices, not sale prices. The estimate answers “what is this listed at”, which is not “what does it sell for”.",
      },
      department: {
        es: "El departamento no es un marco de muestreo limpio: las tarjetas patrocinadas se filtran entre regiones, así que dice dónde se publica el anuncio.",
        en: "Department is not a clean sampling frame: sponsored cards leak between regions, so it says where the listing was published.",
      },
      trim: {
        es: "Falta la versión. El título no la trae, y es justo lo que separa dos ejemplares del mismo modelo. Es la razón principal de que Mercedes-Benz sea el peor segmento en carros.",
        en: "Trim is missing. The title does not carry it, and trim is exactly what separates two units of the same model. It is the main reason Mercedes-Benz is the worst car segment.",
      },
      motoBrand: {
        es: "En motos el 12 % de los títulos no dice qué moto es («Excelente Estado», la dirección del concesionario). Esos anuncios son los que más error acumulan y ya no se arreglan leyendo el título.",
        en: "For motorcycles, 12 % of titles do not say which motorcycle it is (“Excellent condition”, a dealer's address). Those listings carry the most error and can no longer be fixed by parsing the title.",
      },
      fasecolda: {
        es: "No hay comparación contra Fasecolda. La guía no se obtiene por HTTP público y una suscripción está descartada porque el proyecto corre a costo cero, así que se dice que no hay benchmark externo en vez de inventar uno.",
        en: "There is no Fasecolda benchmark. The guide is not reachable over plain HTTP and a subscription is ruled out by the project's zero-cost constraint, so the absence is stated rather than substituted.",
      },
      index: {
        es: "El índice mensual de precios está implementado y probado, y no se publica: exige 180 días de histórico y el lago abarca menos. Con la captura semanal corriendo sola, la fecha es ~2027-03-29.",
        en: "The monthly price index is implemented and tested, and not published: it needs 180 days of history and the lake spans less. With the weekly capture running on its own, that date is ~2027-03-29.",
      },
      time: {
        es: "Las cifras son de un lago con fecha, no constantes del proyecto. Cada captura semanal las mueve, y por eso cada número publicado viaja con el tamaño del lago sobre el que se midió.",
        en: "The figures describe a lake with a date, not project constants. Every weekly capture moves them, which is why each published number travels with the size of the lake it was measured on.",
      },
    },
    repo: { es: "Todo el código, los ADR y el estado detallado", en: "All the code, the ADRs and the detailed status" },
  },
} as const;

/** Pick one language out of a two-language string. */
export function pick(text: Localized, lang: Lang): string {
  return text[lang];
}
