# EcoPerks

EcoPerks is a low-carbon pathfinder that helps users find the most eco-friendly routes while earning rewards at sustainable businesses. This project integrates **OpenRouteService** for multimodal transportation and **geocoding**, along with a **Flask backend** to handle routing, coordinate conversion, and API requests.

.

## **🛠 Tech Stack**

-   **Frontend**: React.js (Axios for API calls)
-   **Backend**: Flask (Python)
-   **APIs Used**:
    -   [OpenRouteService](https://openrouteservice.org/) – Multimodal routing & geocoding

    from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
import logging
from dotenv import load_dotenv
from retrying import retry
import json
import networkx as nx
import numpy as np
from scipy.stats import norm
import random

We used the above pythong libraries.