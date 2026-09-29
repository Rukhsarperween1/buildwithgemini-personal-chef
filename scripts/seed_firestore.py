"""Seed script to populate Firestore with initial recipes for Personal Chef agent."""

from google.cloud import firestore

PROJECT_ID = "qwiklabs-gcp-01-a66c61c823be"
COLLECTION_NAME = "recipes"

SEED_RECIPES = [
    {
        "id": "creamy-tuscan-chicken",
        "title": "Creamy Tuscan Garlic Chicken",
        "cuisine": "Italian",
        "prep_time_minutes": 25,
        "servings": 4,
        "ingredients": [
            "2 large chicken breasts, halved horizontally",
            "1 tbsp olive oil",
            "1 cup heavy cream",
            "1/2 cup chicken broth",
            "1 tsp garlic powder",
            "1 cup spinach",
            "1/2 cup sun-dried tomatoes"
        ],
        "instructions": [
            "Season chicken breasts with salt, pepper, and garlic powder.",
            "Sear chicken in olive oil over medium-high heat until golden (3-5 mins per side), then remove.",
            "In the same skillet, add heavy cream, chicken broth, garlic powder, spinach, and sun-dried tomatoes.",
            "Simmer sauce until spinach wilts and sauce thickens.",
            "Return chicken to skillet and simmer for another 3 minutes before serving."
        ],
        "dietary_tags": ["gluten-free", "low-carb", "keto"]
    },
    {
        "id": "vegetable-thai-green-curry",
        "title": "Vegetable Thai Green Curry",
        "cuisine": "Thai",
        "prep_time_minutes": 30,
        "servings": 4,
        "ingredients": [
            "1 tbsp green curry paste",
            "1 can (14 oz) coconut milk",
            "1 cup vegetable broth",
            "1 cup tofu, cubed",
            "1 cup bell peppers, sliced",
            "1 cup snap peas",
            "Fresh basil leaves for garnish"
        ],
        "instructions": [
            "Heat 2 tbsp of coconut milk cream in a pot over medium heat and fry green curry paste for 2 mins.",
            "Pour in remaining coconut milk and vegetable broth, bring to a gentle simmer.",
            "Add cubed tofu, bell peppers, and snap peas. Cook for 10 minutes until vegetables are tender.",
            "Garnish with fresh basil and serve hot with jasmine rice."
        ],
        "dietary_tags": ["vegan", "vegetarian", "gluten-free", "dairy-free"]
    },
    {
        "id": "classic-avocado-toast",
        "title": "Classic Avocado Toast with Poached Egg",
        "cuisine": "American",
        "prep_time_minutes": 10,
        "servings": 2,
        "ingredients": [
            "2 slices sourdough bread",
            "1 ripe avocado",
            "2 large eggs",
            "1 tbsp lemon juice",
            "Red pepper flakes, salt, and black pepper"
        ],
        "instructions": [
            "Toast sourdough bread slices until crisp.",
            "Mash ripe avocado with lemon juice, salt, and pepper in a small bowl.",
            "Poach eggs in simmering water with a splash of vinegar for 3 minutes.",
            "Spread mashed avocado evenly on toast and top each with a poached egg and red pepper flakes."
        ],
        "dietary_tags": ["vegetarian", "dairy-free"]
    }
]


def seed_database():
    print(f"Connecting to Firestore for project '{PROJECT_ID}'...")
    db = firestore.Client(project=PROJECT_ID)
    recipes_ref = db.collection(COLLECTION_NAME)

    for recipe in SEED_RECIPES:
        doc_id = recipe["id"]
        recipes_ref.document(doc_id).set(recipe)
        print(f"Seeded recipe: {recipe['title']} (ID: {doc_id})")

    print("Seeding complete!")


if __name__ == "__main__":
    seed_database()
