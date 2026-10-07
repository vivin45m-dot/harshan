"""The food commodities tracked by the system.

Each commodity ties three public sources together:

* ``hs_codes`` - six-digit Harmonized System codes under which the US reports
  its monthly imports to UN Comtrade. Where the HS nomenclature split a
  heading during 2013-2026 (shrimp, oysters, cumin...) every code that
  covers the product is listed and the quantities are summed.
* ``fda_terms`` - words that identify the product in an openFDA food
  enforcement (recall) record. Matched against product_description.
* ``nors_terms`` - words that identify the product in the CDC NORS
  ``food_vehicle`` / ``food_contaminated_ingredient`` fields.

The list was chosen around foods that show up repeatedly in FDA recalls and
CDC outbreak investigations and that the US imports in volume, so every
commodity has a demand series and a realistic chance of disruption events.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Commodity:
    key: str
    label: str
    hs_codes: tuple
    fda_terms: tuple
    nors_terms: tuple
    # Words that, when present, mean the record is about a processed product
    # rather than the commodity itself (e.g. "tomato soup").
    exclude: tuple = field(default_factory=tuple)
    perishable: bool = True
    # The commodity is itself a manufactured food, so recalls of snacks or
    # baked goods made from it still belong to its supply chain.
    processed: bool = False


COMMODITIES = [
    Commodity("tomato", "Tomatoes", ("070200",),
              ("tomato", "tomatoes"), ("tomato",),
              exclude=("sauce", "soup", "ketchup", "paste", "juice", "dried", "powder", "chips")),
    Commodity("onion", "Onions & shallots", ("070310",),
              ("onion", "onions", "shallot"), ("onion",),
              exclude=("powder", "rings", "soup", "dip", "chips", "dried", "granulated")),
    Commodity("lettuce", "Lettuce", ("070511", "070519"),
              ("lettuce", "romaine", "iceberg"), ("lettuce", "romaine")),
    Commodity("cucumber", "Cucumbers", ("070700",),
              ("cucumber", "cucumbers"), ("cucumber",),
              exclude=("pickle", "pickles", "relish")),
    Commodity("pepper_fresh", "Fresh peppers", ("070960",),
              ("jalapeno", "jalapeño", "serrano", "bell pepper", "poblano", "habanero"),
              ("jalapeno", "jalapeño", "serrano", "bell pepper", "poblano", "hot pepper"),
              exclude=("powder", "sauce", "flakes", "dried", "crushed red")),
    Commodity("spinach", "Spinach", ("070970",),
              ("spinach",), ("spinach",),
              exclude=("dip", "pasta", "pie", "quiche")),
    Commodity("avocado", "Avocados", ("080440",),
              ("avocado", "avocados", "guacamole"), ("avocado", "guacamole")),
    Commodity("mango", "Mangoes", ("080450",),
              ("mango", "mangoes", "mangos"), ("mango",),
              exclude=("juice", "nectar", "dried", "puree")),
    Commodity("melon", "Cantaloupe & melons", ("080719",),
              ("cantaloupe", "honeydew", "muskmelon"), ("cantaloupe", "honeydew", "melon")),
    Commodity("papaya", "Papayas", ("080720",),
              ("papaya", "papayas"), ("papaya",),
              exclude=("dried", "juice")),
    Commodity("peach", "Peaches & nectarines", ("080930",),
              ("peach", "peaches", "nectarine", "nectarines"), ("peach", "nectarine"),
              exclude=("canned", "syrup", "juice", "pie", "yogurt", "tea")),
    Commodity("strawberry", "Strawberries", ("081010",),
              ("strawberry", "strawberries"), ("strawberry", "strawberries"),
              exclude=("jam", "yogurt", "flavored", "milk", "candy", "syrup")),
    Commodity("frozen_berry", "Frozen berries", ("081120",),
              ("frozen raspberries", "frozen blackberries", "frozen berries", "frozen mixed berries",
               "frozen blueberries"), ("frozen berries", "frozen raspberries", "frozen blackberries")),
    Commodity("black_pepper", "Black pepper", ("090411", "090412"),
              ("black pepper", "ground pepper", "peppercorn"), ("black pepper",), perishable=False),
    Commodity("cinnamon", "Cinnamon", ("090611", "090619", "090620"),
              ("cinnamon",), ("cinnamon",), perishable=False),
    Commodity("cumin", "Cumin", ("090931", "090932"),
              ("cumin",), ("cumin",), perishable=False),
    Commodity("sesame", "Sesame & tahini", ("120740",),
              ("tahini", "sesame seed", "sesame paste"), ("tahini", "sesame"), perishable=False),
    Commodity("shrimp", "Shrimp", ("030617", "160521", "160529"),
              ("shrimp", "prawn", "prawns"), ("shrimp", "prawn")),
    Commodity("oyster", "Oysters", ("030711", "030712", "030719"),
              ("oyster", "oysters"), ("oyster",),
              exclude=("sauce", "crackers", "mushroom")),
    Commodity("clam", "Clams", ("030771", "030772", "030779"),
              ("clam", "clams"), ("clam",),
              exclude=("juice", "chowder", "sauce", "clam shell", "shell container")),
    Commodity("tuna", "Tuna", ("030487",),
              ("tuna",), ("tuna",),
              # HS 030487 is frozen fillets: canned tuna and tuna salads are a different chain.
              exclude=("salad", "spread", "wrap", "canned", " can ", "cans", "in water", "in oil", "pouch")),
    Commodity("fresh_cheese", "Fresh cheese", ("040610",),
              ("queso fresco", "queso blanco", "fresh cheese", "cotija", "panela", "ricotta"),
              ("queso fresco", "queso blanco", "fresh cheese", "soft cheese", "cotija", "panela")),
    Commodity("peanut_butter", "Peanut products", ("200811",),
              ("peanut butter", "peanut paste", "roasted peanut"), ("peanut butter", "peanut")),
    Commodity("infant_formula", "Infant formula", ("190110",),
              ("infant formula",), ("infant formula",), perishable=False, processed=True),
]

BY_KEY = {c.key: c for c in COMMODITIES}

# Finished foods that only contain a commodity as an ingredient. A recall of
# "onion chips" or "mango chili chocolate" says nothing about the onion or
# mango import chain, so these words rule a match out (unless the commodity
# is itself processed, see Commodity.processed).
FINISHED_FOOD = ("chip", "chocolate", "candy", "cookie", "cracker", "snack", "granola", "cereal",
                 "ice cream", "bagel", "pizza", "burrito", "sandwich", "gimbap", "kimbap",
                 "seasoning", "dressing", "soup", "sauce", " dip", "flavored", "flavoured",
                 " bar ", " bars", "cake", "muffin", "pastry", "pie ", "dumpling", "noodle",
                 "popsicle", "fruit pop", "ice pop", "lassi", "drink", "beverage", "smoothie", "margarita",
                 "sorbet", "waffle", "rolls", "brownie", "dough", "chews", "mix ", "bites",
                 "electrolyte", "pedialyte", "polenta", "stir fry", "yogurt", "jam", "jelly",
                 "paleta", "pickle", "truffle", "pudding", "danish", "pecan", "streusel", "custard",
                 "bread", "pastries", "fudge", "coffee", "sour cream", "chowda", "chowder",
                 "shake", "glaze", "tamale", "granita", "food color", "caramel", "potato salad",
                 "pasta salad", "peanut butter cup", "freeze dried", "lemonade", "spanakopita")
