# EcoPerks

EcoPerks is a low-carbon pathfinder that helps users find the most eco-friendly routes while earning rewards at sustainable restaurants. This project integrates **OpenRouteService** for multimodal transportation and **geocoding**, along with a **Flask backend** to handle routing, coordinate conversion, and API requests.

.

## **🛠 Tech Stack**

-   **Frontend**: React.js (Axios for API calls)
-   **Backend**: Flask (Python)
-   **APIs Used**:
    -   [OpenRouteService](https://openrouteservice.org/) – Multimodal routing & geocoding
    -   Google Maps (Optional for visualization)
-   **Database (Future Scope)**: PostgreSQL / Firebase for user rewards tracking

----------

## **📂 Project Structure**

bash

CopyEdit

`EcoPerks/
│── backend/             # Flask backend
│   ├── server.py        # Main backend API
│   ├── utils.py         # Helper functions (geocoding, emissions calculation)
│   ├── config.py        # API keys & environment variables
│   ├── requirements.txt # Python dependencies
│── frontend/            # React frontend (calls Flask API)
│   ├── src/
│   │   ├── services/    # API calls (Axios)
│   │   ├── components/  # UI components
│── README.md            # Project documentation
│── .gitignore           # Ignore unnecessary files` 

----------

## **🚀 How the Backend Works**

### **1️⃣ Address → Coordinates (Geocoding)**

-   The backend receives a **text address** (e.g., `"Princeton University, NJ"`).
-   Calls OpenRouteService’s **Geocoding API** to **convert the address to latitude & longitude**.
-   Returns the coordinates to the frontend.

📌 **API Endpoint:**

http

CopyEdit

`GET /get-coordinates?address=<address>` 

📌 **Example Response:**

json

CopyEdit

`{
  "latitude": 40.3431,
  "longitude": -74.6514
}` 

----------

### **2️⃣ Finding the Best Route (Low-Carbon Pathfinding)**

-   The backend gets **origin & destination addresses** from the frontend.
-   Converts addresses to **coordinates** using OpenRouteService Geocoding.
-   Calls **OpenRouteService Routing API** to find a multimodal route (walking, biking, transit).
-   Returns the **optimized route** with total **CO₂ emissions**.

📌 **API Endpoint:**

http

CopyEdit

`GET /get-route?origin=<origin>&destination=<destination>&mode=<mode>` 

📌 **Example Modes:**

-   `"foot-walking"` 🚶
-   `"cycling-regular"` 🚲
-   `"driving-car"` 🚗
-   `"publicTransport"` 🚌

📌 **Example Response:**

json

CopyEdit

`{
  "route": [
    {"mode": "walking", "distance_km": 1.2},
    {"mode": "bus", "distance_km": 8.5},
    {"mode": "walking", "distance_km": 0.3}
  ],
  "co2_emissions_kg": 0.3
}` 

----------

### **3️⃣ Finding Nearby Eco-Friendly Restaurants**

-   The backend will later integrate **sustainability-focused restaurant databases**.
-   Uses geolocation to **suggest restaurants near the user's route**.
-   Future scope: Integrate **discounts & loyalty rewards**.

📌 **API Endpoint:**

http

CopyEdit

`GET /get-eco-restaurants?lat=<lat>&lon=<lon>` 

📌 **Example Response:**

json

CopyEdit

`{
  "restaurants": [
    {"name": "Green Earth Café", "distance_km": 0.5, "discount": "10%"},
    {"name": "Vegan Bites", "distance_km": 0.8, "discount": "15%"}
  ]
}`