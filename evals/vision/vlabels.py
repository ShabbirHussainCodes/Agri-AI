"""PlantDoc folder name -> the classifier's class string (README.md "Data").

The classifier has 38 PlantVillage classes; PlantDoc has 28 folders, all of which have a counterpart. Two
counterparts are APPROXIMATE (the folder names a symptom, the class names a disease) and are flagged: results
are reported with and without them.
"""

PLANTDOC_TO_CLASS: dict[str, str] = {
    "Apple Scab Leaf": "Apple___Apple_scab",
    "Apple leaf": "Apple___healthy",
    "Apple rust leaf": "Apple___Cedar_apple_rust",
    "Bell_pepper leaf": "Pepper,_bell___healthy",
    "Bell_pepper leaf spot": "Pepper,_bell___Bacterial_spot",  # approximate
    "Blueberry leaf": "Blueberry___healthy",
    "Cherry leaf": "Cherry_(including_sour)___healthy",
    "Corn Gray leaf spot": "Corn_(maize)___Cercospora_leaf_spot Gray_leaf_spot",
    "Corn leaf blight": "Corn_(maize)___Northern_Leaf_Blight",  # approximate
    "Corn rust leaf": "Corn_(maize)___Common_rust_",
    "Peach leaf": "Peach___healthy",
    "Potato leaf early blight": "Potato___Early_blight",
    "Potato leaf late blight": "Potato___Late_blight",
    "Raspberry leaf": "Raspberry___healthy",
    "Soyabean leaf": "Soybean___healthy",
    "Squash Powdery mildew leaf": "Squash___Powdery_mildew",
    "Strawberry leaf": "Strawberry___healthy",
    "Tomato Early blight leaf": "Tomato___Early_blight",
    "Tomato Septoria leaf spot": "Tomato___Septoria_leaf_spot",
    "Tomato leaf": "Tomato___healthy",
    "Tomato leaf bacterial spot": "Tomato___Bacterial_spot",
    "Tomato leaf late blight": "Tomato___Late_blight",
    "Tomato leaf mosaic virus": "Tomato___Tomato_mosaic_virus",
    "Tomato leaf yellow virus": "Tomato___Tomato_Yellow_Leaf_Curl_Virus",
    "Tomato mold leaf": "Tomato___Leaf_Mold",
    "Tomato two spotted spider mites leaf": "Tomato___Spider_mites Two-spotted_spider_mite",
    "grape leaf": "Grape___healthy",
    "grape leaf black rot": "Grape___Black_rot",
}

APPROXIMATE = frozenset({"Bell_pepper leaf spot", "Corn leaf blight"})

# The eval's data sets, by the name stored in the cache.
ID_CALIBRATION = "plantdoc_train"
ID_TEST = "plantdoc_test"
OOD_CALIBRATION = ("rice_cal", "beans_cal", "objects_cal")
OOD_TEST = ("rice_test", "beans_test", "objects_test")
OOD_NAMES = {
    "rice_cal": "rice leaves (field)", "rice_test": "rice leaves (field)",
    "beans_cal": "bean leaves (field)", "beans_test": "bean leaves (field)",
    "objects_cal": "objects, no plants", "objects_test": "objects, no plants",
}
