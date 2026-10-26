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
 *
 * **No figure is written here.** A string that needs a number carries a `{placeholder}`
 * and `fill` puts the measured value in. Every number on this site is read from each
 * vertical's `model.json` or from `docs/results/`, both rewritten when the model is
 * retrained. A number typed into a sentence goes stale silently, and nine of them had by
 * the time anybody checked.
 */

export type Lang = "es" | "en";

export const LANGS: Lang[] = ["es", "en"];

export type Localized = { es: string; en: string };

/** Pick one language out of a two-language string. */
export function pick(text: Localized, lang: Lang): string {
  return text[lang];
}

/**
 * Resolve a string and substitute its `{placeholders}`.
 *
 * Throws on a placeholder with no value rather than rendering the braces. On the market
 * and methodology pages this runs while the static export is being generated, so a
 * forgotten variable is a failed build instead of a `{spread}` someone reads in
 * production.
 */
export function fill(
  text: Localized,
  lang: Lang,
  vars: Record<string, string | number>,
): string {
  return text[lang].replace(/\{(\w+)\}/g, (_match, key: string) => {
    const value = vars[key];
    if (value === undefined) {
      throw new Error(`i18n: no value for {${key}} in "${text[lang]}"`);
    }
    return String(value);
  });
}

export const copy = {
  site: {
    name: { es: "AutoValor CO", en: "AutoValor CO" },
    tagline: {
      es: "Precios de carros y motos usadas en Colombia",
      en: "Used car and motorcycle prices in Colombia",
    },
  },
  nav: {
    value: { es: "Valorar", en: "Value" },
    market: { es: "Mercado", en: "Market" },
    method: { es: "Metodología", en: "Methodology" },
    skip: { es: "Saltar al contenido", en: "Skip to content" },
    menu: { es: "Menú", en: "Menu" },
    close: { es: "Cerrar", en: "Close" },
  },
  lang: {
    label: { es: "Idioma", en: "Language" },
    es: { es: "Español", en: "Spanish" },
    en: { es: "Inglés", en: "English" },
  },
  theme: {
    label: { es: "Tema", en: "Theme" },
    light: { es: "Claro", en: "Light" },
    auto: { es: "Auto", en: "Auto" },
    dark: { es: "Oscuro", en: "Dark" },
  },
  footer: {
    disclaimer: {
      es: "Las estimaciones son informativas y no son un avalúo comercial. Salen de precios pedidos en anuncios publicados.",
      en: "These estimates are informational and are not a commercial appraisal. They come from asking prices in published listings.",
    },
    author: { es: "Hecho por Jose Luis Romo", en: "Built by Jose Luis Romo" },
    repo: { es: "Código en GitHub", en: "Source on GitHub" },
    linkedin: { es: "LinkedIn", en: "LinkedIn" },
    api: { es: "Documentación de la API", en: "API documentation" },
    method: { es: "Cómo se calcula", en: "How this is computed" },
    dataDate: { es: "Datos al {date}", en: "Data to {date}" },
  },

  /** The connection indicator next to the button, and the notice if the wait gets long. */
  status: {
    connecting: { es: "Conectando con el modelo…", en: "Connecting to the model…" },
    ready: { es: "Modelo listo", en: "Model ready" },
    wakingTitle: { es: "El servicio está arrancando", en: "The service is starting up" },
    wakingBody: {
      es: "Estaba inactivo por falta de uso. Esta primera consulta puede tardar cerca de un minuto y las siguientes responden al instante.",
      en: "It had gone idle for lack of traffic. This first request can take about a minute, and the rest answer instantly.",
    },
  },

  hero: {
    title: {
      es: "¿Cuánto vale tu carro o tu moto usada?",
      en: "What is your used car or motorcycle worth?",
    },
    lead: {
      es: "Dinos qué vehículo es y te damos un precio estimado, el rango en el que se piden los anuncios parecidos y qué características lo suben o lo bajan.",
      en: "Tell us which vehicle it is and you get an estimated price, the range comparable listings are asked at, and the features that push it up or down.",
    },
    listingsLabel: { es: "Anuncios analizados", en: "Listings analysed" },
    errorLabel: { es: "Error medio", en: "Average error" },
    errorValue: {
      es: "{car} en carros · {motorcycle} en motos",
      en: "{car} on cars · {motorcycle} on motorcycles",
    },
    dataLabel: { es: "Datos al", en: "Data to" },
  },

  form: {
    groupVehicle: { es: "El vehículo", en: "The vehicle" },
    groupListing: { es: "El anuncio", en: "The listing" },
    vehicleType: { es: "Tipo de vehículo", en: "Vehicle type" },
    car: { es: "Carro", en: "Car" },
    motorcycle: { es: "Moto", en: "Motorcycle" },
    cars: { es: "Carros", en: "Cars" },
    motorcycles: { es: "Motos", en: "Motorcycles" },
    required: { es: "Obligatorio", en: "Required" },
    optional: { es: "Opcional", en: "Optional" },

    brand: { es: "Marca", en: "Make" },
    brandPlaceholder: { es: "Busca una marca", en: "Search makes" },
    model: { es: "Modelo", en: "Model" },
    modelPlaceholder: { es: "Busca un modelo", en: "Search models" },
    modelAfterBrand: { es: "Elige primero la marca", en: "Choose the make first" },
    modelUnknown: { es: "No lo sé", en: "I don't know" },
    year: { es: "Año del modelo", en: "Model year" },
    engine: { es: "Cilindrada", en: "Displacement" },
    engineUnit: { es: "cc", en: "cc" },
    engineHint: {
      es: "Si no la sabes, déjala vacía: el modelo trabaja con el dato ausente.",
      en: "Leave it empty if you do not know it: the model works with the value missing.",
    },
    mileage: { es: "Kilometraje", en: "Mileage" },
    mileageUnit: { es: "km", en: "km" },
    department: { es: "Departamento", en: "Department" },
    departmentLowData: {
      es: "Otros departamentos, con pocos anuncios",
      en: "Other departments, with few listings",
    },
    departmentLowDataHint: {
      es: "Tenemos {count} anuncios de este departamento, así que el estimado es menos preciso.",
      en: "We have {count} listings from this department, so the estimate is less precise.",
    },
    askingPrice: { es: "Precio pedido", en: "Asking price" },
    askingPriceHint: {
      es: "Si lo escribes, lo comparamos contra el rango.",
      en: "If you enter it, we compare it against the range.",
    },

    listingsCount: { es: "{count} anuncios", en: "{count} listings" },
    searchNoMatch: { es: "Nada coincide con «{query}»", en: "Nothing matches “{query}”" },
    modelShowAll: {
      es: "Ver también los modelos con pocos anuncios",
      en: "Show the models with few listings too",
    },
    submit: { es: "Calcular el precio", en: "Estimate the price" },
    submitting: { es: "Calculando…", en: "Estimating…" },
    reset: { es: "Valorar otro", en: "Value another" },

    errors: {
      brand: { es: "Elige una marca.", en: "Choose a make." },
      department: { es: "Elige un departamento.", en: "Choose a department." },
      year: {
        es: "El año tiene que estar entre {min} y {max}.",
        en: "The year has to be between {min} and {max}.",
      },
      mileageMissing: { es: "Escribe el kilometraje.", en: "Enter the mileage." },
      mileageRange: {
        es: "Escribe un kilometraje entre 0 y {max} km.",
        en: "Enter a mileage between 0 and {max} km.",
      },
      price: {
        es: "Escribe el precio en pesos, sin centavos.",
        en: "Enter the price in pesos, with no cents.",
      },
      engineRange: {
        es: "La cilindrada tiene que estar entre {min} y {max} cc.",
        en: "Displacement has to be between {min} and {max} cc.",
      },
    },
  },

  result: {
    heading: { es: "Precio estimado", en: "Estimated price" },
    range: { es: "Rango probable", en: "Likely range" },
    rangeHelp: {
      es: "Ocho de cada diez anuncios parecidos se piden dentro de este rango.",
      en: "Eight in ten comparable listings are asked within this range.",
    },

    emptyTitle: { es: "Qué vas a recibir", en: "What you will get" },
    emptyBody: {
      es: "Un precio estimado, el rango de los anuncios parecidos, la comparación con el precio que pides y los cinco factores que más mueven el valor.",
      en: "An estimated price, the range of comparable listings, how your asking price compares, and the five factors that move the value most.",
    },
    exampleBadge: { es: "Ejemplo", en: "Example" },

    asking: { es: "Precio pedido", en: "Asking price" },
    askingAbove: {
      es: "Pides {pct} más que el estimado.",
      en: "You are asking {pct} above the estimate.",
    },
    askingBelow: {
      es: "Pides {pct} menos que el estimado.",
      en: "You are asking {pct} below the estimate.",
    },
    askingEqual: {
      es: "Pides casi exactamente el estimado.",
      en: "You are asking almost exactly the estimate.",
    },

    bargain: { es: "Ganga", en: "Bargain" },
    bargainWhy: {
      es: "El precio pedido queda por debajo del rango de los anuncios parecidos.",
      en: "The asking price sits below the range of comparable listings.",
    },
    fair: { es: "Justo", en: "Fair" },
    fairWhy: {
      es: "El precio pedido queda dentro del rango de los anuncios parecidos.",
      en: "The asking price falls inside the range of comparable listings.",
    },
    expensive: { es: "Caro", en: "Expensive" },
    expensiveWhy: {
      es: "El precio pedido queda por encima del rango de los anuncios parecidos.",
      en: "The asking price sits above the range of comparable listings.",
    },

    noLabelTitle: { es: "Precio y rango, sin calificar", en: "Price and range, no rating" },
    noLabelBody: {
      es: "Te damos el precio estimado y el rango. No decimos si el anuncio es una ganga o está caro, porque la medición de este tipo de vehículo no alcanza para sostenerlo.",
      en: "You get the estimated price and the range. We do not say whether the listing is a bargain or expensive, because the measurement for this kind of vehicle does not support it.",
    },
    /** One per gate failure code the model publishes, so the reason is read in Spanish. */
    precision: {
      widthAboveMax: {
        es: "El rango mide {value} del precio estimado, por encima del {limit} que pedimos para calificar un anuncio.",
        en: "The range measures {value} of the estimated price, above the {limit} we require before rating a listing.",
      },
      coverageBelowMin: {
        es: "El rango contiene el precio en {value} de los casos, por debajo del {limit} que pedimos.",
        en: "The range contains the price in {value} of cases, below the {limit} we require.",
      },
      coverageAboveMax: {
        es: "El rango contiene el precio en {value} de los casos, por encima del {limit} que pedimos. Un rango que cubre de más mete en «justo» anuncios que están mal preciados.",
        en: "The range contains the price in {value} of cases, above the {limit} we require. A range that covers too much absorbs genuinely mispriced listings into “fair”.",
      },
      unknown: {
        es: "La medición del rango no alcanza para calificar este anuncio.",
        en: "The range measurement is not enough to rate this listing.",
      },
    },

    factors: { es: "Qué mueve este precio", en: "What moves this price" },
    factorsHelp: {
      es: "Cada factor multiplica el precio base de su tipo de vehículo. El precio base por todos los factores da el estimado.",
      en: "Each factor multiplies the base price for its kind of vehicle. The base price times every factor gives the estimate.",
    },
    raises: { es: "sube", en: "raises" },
    lowers: { es: "baja", en: "lowers" },
    basePrice: { es: "Precio base", en: "Base price" },
    modelVersion: { es: "Modelo del {date}", en: "Model from {date}" },
    howItWorks: { es: "Cómo se calcula", en: "How this is computed" },
    copyLink: { es: "Copiar enlace", en: "Copy link" },
    copied: { es: "Enlace copiado", en: "Link copied" },

    errors: {
      offlineTitle: { es: "Sin conexión con el servicio", en: "No connection to the service" },
      offlineBody: {
        es: "Revisa tu conexión y vuelve a intentar.",
        en: "Check your connection and try again.",
      },
      wakingTitle: { es: "El servicio está arrancando", en: "The service is starting up" },
      wakingBody: {
        es: "Vuelve a intentar en unos segundos.",
        en: "Try again in a few seconds.",
      },
      noDataTitle: { es: "Faltan anuncios para estimar", en: "Not enough listings to estimate" },
      noDataBody: {
        es: "No tenemos suficientes anuncios de esa marca y ese modelo para dar un precio.",
        en: "We do not have enough listings of that make and model to give a price.",
      },
      unexpectedTitle: { es: "No pudimos calcular el precio", en: "We could not compute the price" },
      unexpectedBody: {
        es: "Vuelve a intentar. Si sigue pasando, el detalle de abajo dice qué respondió el servicio.",
        en: "Try again. If it keeps happening, the detail below says what the service answered.",
      },
      detail: { es: "Detalle técnico", en: "Technical detail" },
      retry: { es: "Reintentar", en: "Try again" },
    },
  },

  market: {
    heading: { es: "Qué dice el mercado", en: "What the market says" },
    lead: {
      es: "Cuánto valor pierde un vehículo cada año, cuánto se cobra el kilometraje y dónde se pide más caro el mismo vehículo.",
      en: "How much value a vehicle loses each year, how much mileage is charged for, and where the same vehicle is asked at more.",
    },
    leadDetail: {
      es: "Las cifras salen de una regresión de precios, que separa cuánto aporta cada característica por separado (una regresión hedónica, en la jerga). Cada estimación lleva su margen al 95 %, y cuando ese margen pasa por el cero lo marcamos.",
      en: "The figures come from a price regression, which separates what each feature contributes on its own (a hedonic regression, in the jargon). Every estimate carries its 95 % margin, and we mark the ones whose margin crosses zero.",
    },
    measuredOn: {
      es: "{cars} carros y {motorcycles} motos · datos al {date}",
      en: "{cars} cars and {motorcycles} motorcycles · data to {date}",
    },
    notSignificant: { es: "no se distingue de cero", en: "indistinguishable from zero" },
    reference: { es: "referencia", en: "reference" },
    insightLabel: { es: "Lectura", en: "Reading" },

    findingsTitle: { es: "Lo que encontramos", en: "What we found" },
    findings: {
      flatMotoTitle: {
        es: "Una moto casi no pierde valor con los años",
        en: "A motorcycle barely loses value with age",
      },
      flatMotoBody: {
        es: "Una {brand} pierde {pct} al año, y la medición no la distingue de no perder nada.",
        en: "A {brand} loses {pct} a year, and the measurement cannot tell it apart from losing nothing.",
      },
      mileageTitle: {
        es: "10.000 km en un carro de precio medio",
        en: "10,000 km on a mid-priced car",
      },
      mileageBody: {
        es: "Bajan el precio pedido {amount}, sobre una mediana de {median}.",
        en: "They take {amount} off the asking price, against a median of {median}.",
      },
      regionalTitle: {
        es: "La misma moto se pide más caro en {department}",
        en: "The same motorcycle is asked at more in {department}",
      },
      regionalBody: {
        es: "{pct} por encima de Bogotá, con el mismo modelo, la misma edad y el mismo kilometraje.",
        en: "{pct} above Bogotá, at the same model, age and mileage.",
      },
      tenYearsTitle: { es: "A los {age} años", en: "At {age} years" },
      tenYearsBody: {
        es: "Un {carBrand} conserva {carPct} de su valor y una {motoBrand}, {motoPct}.",
        en: "A {carBrand} keeps {carPct} of its value and a {motoBrand}, {motoPct}.",
      },
    },

    depreciation: {
      title: { es: "Cuánto pierde cada marca al año", en: "What each make loses a year" },
      lead: {
        es: "El valor que pierde un vehículo por cada año que cumple, con el kilometraje de un año típico ya incluido.",
        en: "The value a vehicle loses for each year it ages, with a typical year's mileage already included.",
      },
      insightCar: {
        es: "{lowBrand} pierde {lowPct} al año y {highBrand} pierde {highPct}, casi el doble. Sobre un carro de {median}, esa diferencia son {gap} cada año.",
        en: "{lowBrand} loses {lowPct} a year and {highBrand} loses {highPct}, nearly twice as fast. On a {median} car that gap is {gap} every year.",
      },
      insightMoto: {
        es: "{refBrand} pierde {refPct} al año y su margen pasa por el cero, así que estos datos no la distinguen de no perder nada. {highBrand} pierde {highPct}. En las marcas que aguantan, una moto usada cuesta casi lo mismo que una nueva.",
        en: "{refBrand} loses {refPct} a year and its margin crosses zero, so this data cannot tell it apart from losing nothing. {highBrand} loses {highPct}. For the makes that hold value, a used motorcycle costs close to a new one.",
      },
    },

    retained: {
      title: {
        es: "Qué parte del valor queda con los años",
        en: "What share of the value is left over time",
      },
      lead: {
        es: "La misma estimación vista como curva, del primer año al año {age}.",
        en: "The same estimate seen as a curve, from the first year to year {age}.",
      },
      insight: {
        es: "A los {age} años un {carBrand} conserva {carPct} y una {motoBrand}, {motoPct}. Las curvas de las motos son casi planas y las de los carros bajan.",
        en: "At {age} years a {carBrand} keeps {carPct} and a {motoBrand}, {motoPct}. The motorcycle curves are nearly flat and the car curves fall.",
      },
      curveNote: {
        es: "Mostramos la marca que más conserva, la que menos y la de referencia.",
        en: "We show the make that holds most, the one that holds least, and the reference.",
      },
      axisAge: { es: "Edad (años)", en: "Age (years)" },
      axisRetained: { es: "Valor que queda", en: "Value left" },
    },

    mileage: {
      title: { es: "Cuánto cuestan 10.000 km", en: "What 10,000 km cost" },
      lead: {
        es: "Lo que baja el precio pedido por cada 10.000 km más en el odómetro, medido en la mediana de precio de cada grupo.",
        en: "What 10,000 more kilometres take off the asking price, measured at each group's median price.",
      },
      leadDetail: {
        es: "Los grupos se cortan por la clase de precio del vehículo, que sale de su marca y su modelo. Cortarlos por el precio del propio anuncio produciría un efecto falso.",
        en: "The groups are cut by the vehicle's price class, which comes from its make and model. Cutting them by the listing's own price would produce a false effect.",
      },
      insight: {
        es: "En el carro de precio medio 10.000 km valen {median}, y en el cuartil más caro {top}. En {flatCount} de los cuatro cuartiles de carros el efecto no se distingue de cero, así que el kilometraje no explica el precio por sí solo.",
        en: "On the mid-priced car 10,000 km are worth {median}, and in the dearest quartile {top}. In {flatCount} of the four car quartiles the effect is indistinguishable from zero, so mileage does not explain the price on its own.",
      },
      segmentAll: { es: "todo el grupo", en: "the whole group" },
      quartile: { es: "Cuartil {n}", en: "Quartile {n}" },
      medianLabel: { es: "mediana {amount}", en: "median {amount}" },
    },

    regional: {
      title: {
        es: "Dónde se pide más caro el mismo vehículo",
        en: "Where the same vehicle is asked at more",
      },
      lead: {
        es: "Diferencia frente a Bogotá para un vehículo comparable: mismo modelo, misma edad, mismo kilometraje y misma cilindrada.",
        en: "The difference against Bogotá for a comparable vehicle: same model, same age, same mileage, same displacement.",
      },
      insightCar: {
        es: "En carros el país se comporta casi como un solo mercado: entre el departamento más caro y el más barato hay {spread}, que sobre un carro de {median} son {amount}.",
        en: "For cars the country behaves almost as a single market: between the dearest and the cheapest department there are {spread}, which on a {median} car comes to {amount}.",
      },
      insightMoto: {
        es: "En motos la diferencia llega a {spread}. La misma moto se pide {high} por encima de Bogotá en {highDept} y {low} por debajo en {lowDept}.",
        en: "For motorcycles the difference reaches {spread}. The same motorcycle is asked {high} above Bogotá in {highDept} and {low} below it in {lowDept}.",
      },
      caveat: {
        es: "El departamento dice dónde se publicó el anuncio, que se parece al lugar donde está el vehículo sin ser lo mismo.",
        en: "The department says where the listing was published, which resembles where the vehicle is without being the same thing.",
      },
    },

    catalogue: {
      title: { es: "Por qué las motos son el caso difícil", en: "Why motorcycles are the hard case" },
      lead: {
        es: "Cómo se reparte el peso del modelo entre lo que el vehículo es y cómo está.",
        en: "How the model's weight splits between what the vehicle is and what condition it is in.",
      },
      identity: { es: "Identidad", en: "Identity" },
      identityHelp: { es: "marca, modelo y cilindrada", en: "make, model and displacement" },
      condition: { es: "Estado", en: "Condition" },
      conditionHelp: { es: "edad y kilometraje", en: "age and mileage" },
      other: { es: "Otros", en: "Other" },
      insight: {
        es: "En motos la identidad pesa {motoRatio} veces lo que pesa el estado; en carros, {carRatio}. La regresión de precios lo confirma por otra vía: la edad mueve muy poco el precio de una moto. Así se comporta el mercado, y es la razón por la que en motos publicamos precio y rango sin calificar el anuncio.",
        en: "For motorcycles identity weighs {motoRatio} times what condition does; for cars, {carRatio}. The price regression confirms it independently: age barely moves a motorcycle's price. That is how the market behaves, and it is why motorcycles ship a price and a range with no rating.",
      },
    },

    methodNote: {
      es: "Cada cifra de esta página se lee de los archivos que publica el proyecto y se rehace con cada captura.",
      en: "Every figure on this page is read from the files the project publishes, and is rebuilt with each capture.",
    },
  },

  method: {
    heading: { es: "Cómo se calcula", en: "How this is computed" },
    lead: {
      es: "De dónde salen los datos, cómo se entrena el modelo, cuánto se equivoca y qué no sabe.",
      en: "Where the data comes from, how the model is trained, how wrong it is, and what it does not know.",
    },
    leadDetail: {
      es: "Las cifras de esta página se leen del archivo del modelo publicado, así que cambian cuando cambia el modelo. La página se rehace en cada publicación.",
      en: "The figures on this page are read from the published model's own file, so they change when the model changes. The page is rebuilt on every release.",
    },
    publishedOn: { es: "Publicado el {date}", en: "Published on {date}" },
    modelVersion: { es: "Modelo del {date}", en: "Model from {date}" },
    captures: {
      es: "{count} capturas entre el {first} y el {last}",
      en: "{count} captures between {first} and {last}",
    },

    cards: {
      errorCarLabel: { es: "Error medio en carros", en: "Average error on cars" },
      errorCarCaption: {
        es: "Cuánto se desvía el estimado del precio pedido, en promedio, sobre {count} anuncios que el modelo no vio.",
        en: "How far the estimate lands from the asking price on average, over {count} listings the model never saw.",
      },
      errorMotoLabel: { es: "Error medio en motos", en: "Average error on motorcycles" },
      errorMotoCaption: {
        es: "La misma medición en motos, sobre {count} anuncios apartados.",
        en: "The same measurement on motorcycles, over {count} held-out listings.",
      },
      coverageLabel: { es: "Acierto del rango", en: "Range accuracy" },
      coverageCaption: {
        es: "Carros {car} y motos {motorcycle}, contra el 80 % que el rango promete.",
        en: "Cars {car} and motorcycles {motorcycle}, against the 80 % the range promises.",
      },
      evaluatedLabel: { es: "Anuncios de evaluación", en: "Listings held out" },
      evaluatedCaption: {
        es: "{car} carros y {motorcycle} motos apartados antes de entrenar.",
        en: "{car} cars and {motorcycle} motorcycles set aside before training.",
      },
    },

    toc: {
      label: { es: "En esta página", en: "On this page" },
      data: { es: "Datos y privacidad", en: "Data and privacy" },
      model: { es: "Cómo funciona el modelo", en: "How the model works" },
      results: { es: "Resultados", en: "Results" },
      rule: { es: "La regla de la etiqueta", en: "The label rule" },
      scope: { es: "Alcance y supuestos", en: "Scope and assumptions" },
      links: { es: "Para mirar el detalle", en: "Where to look further" },
    },

    data: {
      title: { es: "Datos y privacidad", en: "Data and privacy" },
      body: {
        es: "Usamos anuncios públicos de TuCarro. El capturador respeta robots.txt, espera entre peticiones y se identifica. No guardamos ningún dato personal de los vendedores, como exige la Ley 1581 de 2012.",
        en: "We use public TuCarro listings. The capture client respects robots.txt, waits between requests and identifies itself. We never store sellers' personal data, as Colombian law 1581 of 2012 requires.",
      },
      askingTitle: { es: "Son precios pedidos, no precios de cierre", en: "These are asking prices, not closing prices" },
      askingBody: {
        es: "En un mercado donde se regatea, lo que se pide queda por encima de lo que se paga. Esa diferencia no está medida aquí.",
        en: "In a market where people haggle, what is asked sits above what is paid. That difference is not measured here.",
      },
      reproducible: {
        es: "Cada captura queda publicada en el repositorio, así que cualquier cifra se puede rehacer desde el principio.",
        en: "Every capture is published in the repository, so any figure can be rebuilt from the start.",
      },
      capturesLink: { es: "Ver las capturas publicadas", en: "See the published captures" },
    },

    model: {
      title: { es: "Cómo funciona el modelo", en: "How the model works" },
      lead: {
        es: "Carros y motos se valoran con modelos separados porque sus precios se comportan distinto.",
        en: "Cars and motorcycles are valued by separate models because their prices behave differently.",
      },
      detail: {
        es: "Como referencia usamos una regresión de precios (OLS). El modelo publicado, LightGBM, reduce el error medio {car} en carros y {motorcycle} en motos. Casi toda la mejora viene de usar marca, modelo y ciudad tal como aparecen, sin agruparlos antes.",
        en: "As a reference we use a price regression (OLS). The published model, LightGBM, cuts the average error by {car} on cars and {motorcycle} on motorcycles. Nearly all of the gain comes from using make, model and city as they appear, without grouping them first.",
      },
      stepsTitle: { es: "De un anuncio a un precio", en: "From a listing to a price" },
      steps: {
        captureTitle: { es: "Captura", en: "Capture" },
        captureBody: {
          es: "Leemos los anuncios publicados de TuCarro una vez por semana.",
          en: "We read TuCarro's published listings once a week.",
        },
        rawTitle: { es: "Capa cruda", en: "Raw layer" },
        rawBody: {
          es: "Cada captura se guarda tal como llegó y no se vuelve a tocar.",
          en: "Each capture is stored exactly as it arrived and is never touched again.",
        },
        featuresTitle: { es: "Limpieza y variables", en: "Cleaning and features" },
        featuresBody: {
          es: "Del título salen marca, modelo y cilindrada. Del anuncio, año, kilometraje y departamento.",
          en: "Make, model and displacement come from the title. Year, mileage and department come from the listing.",
        },
        baselineTitle: { es: "Referencia", en: "Reference" },
        baselineBody: {
          es: "Una regresión de precios marca el error que el modelo publicado tiene que superar.",
          en: "A price regression sets the error the published model has to beat.",
        },
        modelTitle: { es: "Modelo publicado", en: "Published model" },
        modelBody: {
          es: "LightGBM estima el precio, y otros tres modelos estiman los extremos del rango.",
          en: "LightGBM estimates the price, and three more models estimate the ends of the range.",
        },
        calibrationTitle: { es: "Calibración", en: "Calibration" },
        calibrationBody: {
          es: "Medimos cuánto le falta al rango para acertar el 80 % de las veces y lo ensanchamos esa cantidad.",
          en: "We measure how far the range falls short of being right 80 % of the time, and widen it by that much.",
        },
        serveTitle: { es: "Servicio y página", en: "Service and page" },
        serveBody: {
          es: "El modelo entrenado se publica como archivo, el formulario lo consulta y esta página lee sus cifras.",
          en: "The trained model is published as a file, the form queries it, and this page reads its figures.",
        },
      },
      bandTitle: { es: "De dónde sale el rango", en: "Where the range comes from" },
      bandBody: {
        es: "El rango va del precio que supera el 10 % más barato de los anuncios parecidos al que supera el 90 %, lo que deja ocho de cada diez dentro.",
        en: "The range runs from the price that beats the cheapest 10 % of comparable listings to the one that beats 90 %, which leaves eight in ten inside.",
      },
      bandDetail: {
        es: "Sin calibrar, ese rango acertaba en {car} de los casos en carros y {motorcycle} en motos, bastante por debajo del 80 % que promete. La calibración mide ese faltante en anuncios apartados y ensancha el rango esa cantidad.",
        en: "Uncalibrated, that range was right in {car} of cases on cars and {motorcycle} on motorcycles, well under the 80 % it promises. Calibration measures the shortfall on held-out listings and widens the range by it.",
      },
    },

    results: {
      title: { es: "Resultados", en: "Results" },
      lead: {
        es: "Medimos sobre anuncios que ningún modelo vio al entrenarse ni al afinarse.",
        en: "We measure on listings no model saw while training or tuning.",
      },
      detail: {
        es: "El mismo vehículo se vuelve a publicar con otro identificador, así que esos anuncios se apartan en bloque. Separarlos uno por uno dejaba copias a los dos lados y mejoraba el resultado sin razón.",
        en: "The same vehicle gets republished under another identifier, so those listings are set aside as a block. Separating them one by one left copies on both sides and improved the result for no reason.",
      },
      tableCaption: {
        es: "Error y rango de cada tipo de vehículo, medidos sobre los anuncios apartados.",
        en: "Error and range for each kind of vehicle, measured on the held-out listings.",
      },
      columnType: { es: "Tipo", en: "Type" },
      columnError: { es: "Error medio", en: "Average error" },
      columnMedianError: { es: "Error típico", en: "Typical error" },
      columnCoverage: { es: "Acierto del rango", en: "Range accuracy" },
      columnWidth: { es: "Ancho del rango", en: "Range width" },
      columnEvaluated: { es: "Anuncios evaluados", en: "Listings evaluated" },
      columnLabel: { es: "Etiqueta", en: "Label" },
      published: { es: "Publicada", en: "Published" },
      withheld: { es: "Retenida", en: "Withheld" },

      temporalTitle: { es: "Entrenar con el pasado", en: "Training on the past" },
      temporalBody: {
        es: "Medimos también entrenando con los anuncios más antiguos y evaluando con los más recientes. El error sube {car} en carros y {motorcycle} en motos, que es la degradación esperada al estimar una semana hacia adelante.",
        en: "We also measure by training on the oldest listings and evaluating on the newest. The error rises {car} on cars and {motorcycle} on motorcycles, which is the expected decay when estimating a week ahead.",
      },
      temporalCaveat: {
        es: "Con {count} capturas el corte no cae en una fecha limpia: una misma captura queda repartida entre entrenamiento y evaluación. Lo que esto mide es el quinto de anuncios visto más recientemente.",
        en: "With {count} captures the cut does not land on a clean date: one capture ends up split between training and evaluation. What this measures is the most recently seen fifth of the listings.",
      },

      calibrationTitle: { es: "El rango antes y después de calibrarlo", en: "The range before and after calibration" },
      calibrationBody: {
        es: "Sin calibrar, el rango acierta menos de lo que promete. La calibración lo corrige con lo medido en anuncios apartados.",
        en: "Uncalibrated, the range is right less often than it promises. Calibration corrects it with what was measured on held-out listings.",
      },
      calibrationUncalibrated: { es: "Sin calibrar", en: "Uncalibrated" },
      calibrationCalibrated: { es: "Calibrado", en: "Calibrated" },
      calibrationTarget: { es: "Objetivo 80 %", en: "80 % target" },

      baselineTitle: { es: "La referencia y el modelo publicado", en: "The reference and the published model" },
      baselineBody: {
        es: "La regresión de precios es la vara: un modelo que no la supere no se publica.",
        en: "The price regression is the yardstick: a model that does not beat it is not published.",
      },
      baselineLabel: { es: "Regresión de precios", en: "Price regression" },
      servedLabel: { es: "Modelo publicado", en: "Published model" },

      brandErrorTitle: { es: "Dónde se equivoca más", en: "Where it is most wrong" },
      brandErrorBody: {
        es: "Error medio por marca, en carros. {brand} es la más difícil con {value}, y la razón está en el alcance: el título no trae la versión del vehículo.",
        en: "Average error by make, on cars. {brand} is the hardest at {value}, and the reason is in the scope section: the title does not carry the vehicle's trim.",
      },
    },

    rule: {
      title: { es: "La regla de la etiqueta", en: "The label rule" },
      lead: {
        es: "Calificamos un anuncio como ganga, justo o caro solo si el rango de ese tipo de vehículo aguanta dos pruebas.",
        en: "We rate a listing as a bargain, fair or expensive only if that vehicle type's range passes two tests.",
      },
      coverageTitle: {
        es: "Acertar entre el {min} y el {max} de las veces",
        en: "Be right between {min} and {max} of the time",
      },
      coverageWhy: {
        es: "La ventana tiene dos lados a propósito. Un rango que acierta de menos marca «ganga» anuncios normales, y uno que acierta de más mete en «justo» anuncios mal preciados.",
        en: "The window is two-sided on purpose. A range that is right too rarely flags ordinary listings as bargains, and one that is right too often absorbs mispriced listings into “fair”.",
      },
      widthTitle: {
        es: "Medir {max} del precio estimado o menos",
        en: "Measure {max} of the estimated price or less",
      },
      widthWhy: {
        es: "Un rango más ancho que eso abarca casi cualquier precio, así que calificar con él no aporta información.",
        en: "A range wider than that spans almost any price, so a rating based on it carries no information.",
      },
      stateTitle: { es: "Cómo va cada tipo de vehículo", en: "How each vehicle type stands" },
      statePass: { es: "Cumple", en: "Passes" },
      stateFail: { es: "No cumple", en: "Fails" },
      inArtifact: {
        es: "La decisión se toma al entrenar y viaja dentro del archivo del modelo, así que el servicio no la vuelve a calcular. Cuando el rango de motos se angoste, la etiqueta aparece sin que nadie la active.",
        en: "The decision is taken at training time and travels inside the model's file, so the service never re-derives it. When the motorcycle range tightens, the label appears without anyone switching it on.",
      },
    },

    scope: {
      title: { es: "Alcance y supuestos", en: "Scope and assumptions" },
      lead: {
        es: "Lo que este proyecto no sabe, y qué efecto tiene en el estimado.",
        en: "What this project does not know, and what effect that has on the estimate.",
      },
      what: { es: "Qué pasa", en: "What happens" },
      effect: { es: "Cómo afecta al estimado", en: "How it affects the estimate" },
      plan: { es: "Qué está previsto", en: "What is planned" },
      noPlan: { es: "Sin plan por ahora", en: "No plan for now" },
      outOfScope: { es: "Fuera de alcance", en: "Out of scope" },

      items: {
        sourceWhat: { es: "Todo sale de un solo sitio, TuCarro.", en: "Everything comes from one site, TuCarro." },
        sourceEffect: {
          es: "Lo que describimos es ese mercado y no el país entero.",
          en: "What we describe is that marketplace rather than the whole country.",
        },
        askingWhat: { es: "Trabajamos con precios pedidos.", en: "We work with asking prices." },
        askingEffect: {
          es: "El estimado dice por cuánto se publica un vehículo, y lo que se paga suele ser menos.",
          en: "The estimate says what a vehicle is listed at, and what gets paid is usually less.",
        },
        askingPlan: {
          es: "Los precios de cierre no son públicos, así que no hay forma de medir la diferencia.",
          en: "Closing prices are not public, so there is no way to measure the gap.",
        },
        trimWhat: { es: "El título no trae la versión del vehículo.", en: "The title does not carry the vehicle's trim." },
        trimEffect: {
          es: "Dos ejemplares del mismo modelo con equipamiento distinto reciben el mismo estimado. Por eso {brand} es la marca con más error, {value}.",
          en: "Two units of the same model with different equipment get the same estimate. That is why {brand} is the make with the most error, {value}.",
        },
        motoBrandWhat: {
          es: "En {pct} de los anuncios de motos el título no dice qué moto es.",
          en: "In {pct} of motorcycle listings the title does not say which motorcycle it is.",
        },
        motoBrandEffect: {
          es: "Esos anuncios acumulan el error más alto de su tipo, porque el modelo estima sin saber la identidad del vehículo.",
          en: "Those listings carry the highest error of their type, because the model estimates without knowing the vehicle's identity.",
        },
        departmentWhat: {
          es: "El departamento sale del anuncio, y las tarjetas patrocinadas se filtran entre regiones.",
          en: "The department comes from the listing, and sponsored cards leak between regions.",
        },
        departmentEffect: {
          es: "La comparación regional dice dónde se publicó el anuncio.",
          en: "The regional comparison says where the listing was published.",
        },
        fasecoldaWhat: {
          es: "No comparamos contra la guía de valores de Fasecolda.",
          en: "We do not compare against the Fasecolda value guide.",
        },
        fasecoldaEffect: {
          es: "No hay una referencia externa contra la que contrastar el estimado.",
          en: "There is no external reference to check the estimate against.",
        },
        fasecoldaPlan: {
          es: "La guía no se consigue por vía pública y una suscripción está descartada, así que la ausencia se dice en vez de reemplazarla.",
          en: "The guide is not available publicly and a subscription is ruled out, so the absence is stated rather than substituted.",
        },
        indexWhat: {
          es: "No publicamos el índice mensual de precios.",
          en: "We do not publish the monthly price index.",
        },
        indexEffect: {
          es: "No se puede ver si el mercado sube o baja mes a mes.",
          en: "There is no way to see whether the market rises or falls month to month.",
        },
        indexPlan: {
          es: "Está escrito y probado. Se publica cuando las capturas semanales acumulen seis meses de historia, hacia {date}.",
          en: "It is written and tested. It gets published once the weekly captures have six months of history, around {date}.",
        },
        timeWhat: {
          es: "Las cifras describen los anuncios capturados hasta una fecha.",
          en: "The figures describe the listings captured up to a date.",
        },
        timeEffect: {
          es: "Cada captura semanal las mueve, así que cada número viaja con la fecha y el número de anuncios sobre los que se midió.",
          en: "Every weekly capture moves them, so each number travels with the date and the number of listings it was measured on.",
        },
        timePlan: {
          es: "Se recalculan cada vez que el modelo se vuelve a publicar.",
          en: "They are recomputed every time the model is published again.",
        },
      },
    },

    links: {
      title: { es: "Para mirar el detalle", en: "Where to look further" },
      repo: { es: "Código en GitHub", en: "Source on GitHub" },
      api: { es: "Documentación de la API", en: "API documentation" },
      modelInfo: { es: "Lo que el modelo reporta de sí mismo", en: "What the model reports about itself" },
      decisions: { es: "Decisiones técnicas", en: "Technical decisions" },
      status: { es: "Estado detallado del proyecto", en: "Detailed project status" },
      author: { es: "Hecho por Jose Luis Romo", en: "Built by Jose Luis Romo" },
    },
  },

  /**
   * Short definitions for the terms that cannot be avoided, shown the first time each one
   * appears. Jargon with a definition attached is a reader who learns something; jargon
   * without one is a reader who leaves.
   */
  terms: {
    averageError: {
      term: { es: "error medio", en: "average error" },
      definition: {
        es: "Promedio de cuánto se desvía el estimado del precio pedido, en porcentaje. Un 10 % quiere decir que, en promedio, el estimado queda 10 % arriba o abajo.",
        en: "The average distance between the estimate and the asking price, in percent. 10 % means the estimate lands 10 % above or below on average.",
      },
    },
    range: {
      term: { es: "rango probable", en: "likely range" },
      definition: {
        es: "El intervalo donde se piden ocho de cada diez anuncios parecidos. Fuera quedan el 10 % más barato y el 10 % más caro.",
        en: "The interval eight in ten comparable listings are asked within. The cheapest 10 % and the dearest 10 % fall outside.",
      },
    },
    heldOut: {
      term: { es: "anuncios apartados", en: "held-out listings" },
      definition: {
        es: "Anuncios separados antes de entrenar, que el modelo no vio. Medir sobre ellos es la única forma de saber si acierta en casos nuevos.",
        en: "Listings set aside before training, which the model never saw. Measuring on them is the only way to know whether it works on new cases.",
      },
    },
    calibration: {
      term: { es: "calibración", en: "calibration" },
      definition: {
        es: "Ensanchar el rango por lo que le faltaba para acertar el 80 % de las veces, medido en anuncios apartados.",
        en: "Widening the range by what it needed to be right 80 % of the time, measured on held-out listings.",
      },
    },
    factors: {
      term: { es: "factores", en: "factors" },
      definition: {
        es: "El reparto del precio estimado entre las características del vehículo. Cada factor multiplica el precio base, y el resultado es exacto.",
        en: "How the estimated price splits across the vehicle's features. Each factor multiplies the base price, and the result is exact.",
      },
    },
    priceRegression: {
      term: { es: "regresión de precios", en: "price regression" },
      definition: {
        es: "Un modelo que estima cuánto aporta al precio cada característica por separado, con su margen de error.",
        en: "A model that estimates what each feature contributes to the price on its own, with its margin of error.",
      },
    },
    margin: {
      term: { es: "margen al 95 %", en: "95 % margin" },
      definition: {
        es: "El intervalo donde está el valor real con 95 % de probabilidad. Si pasa por el cero, estos datos no distinguen el efecto de cero.",
        en: "The interval the true value sits in with 95 % probability. If it crosses zero, this data cannot tell the effect apart from zero.",
      },
    },
  },
} as const;
