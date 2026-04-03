from flask import Flask, request, jsonify
import numpy as np
import pandas as pd
import joblib
import os
import sys

# get base directory of this file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# allow importing ensemble class
sys.path.append(os.path.join(BASE_DIR,"credit_risk_predictor","final_model"))
from ensemble_model import CreditEnsembleModel

app = Flask(__name__)

# load models using safe paths
credit_model = joblib.load(
    os.path.join(BASE_DIR,"credit_risk_predictor","final_model", "credit_ensemble.pkl")
)

forecast_model = joblib.load(
    os.path.join(BASE_DIR,"demand_forecaster", "final_model", "demand_pipeline.pkl")
)


# multi-step forecasting
def multi_step_forecast(model, data, days=14):
    predictions = []
    current = data.copy()

    for i in range(days):

        features = pd.DataFrame([current])

        pred_log = model.predict(features)[0]
        pred = np.expm1(pred_log)

        predictions.append(round(float(pred), 2))

        # update lag features
        current["lag_14"] = current["lag_7"]
        current["lag_7"] = current["lag_1"]
        current["lag_1"] = pred

        # update rolling mean
        current["rolling_mean_7"] = (
            current["rolling_mean_7"] * 6 + pred
        ) / 7

        # update date features
        current["day_of_week"] = (current["day_of_week"] + 1) % 7
        current["day_of_month"] += 1

        if current["day_of_month"] > 30:
            current["day_of_month"] = 1
            current["month"] += 1

    return predictions


@app.route("/")
def home():
    return "GrocerSmart AI API is running"


# credit risk prediction
@app.route("/predict/credit", methods=["POST"])
def predict_credit():
    try:
        data = request.json

        if not data:
            return jsonify({"error": "No input data"}), 400

        required_fields = [
            "credit_limit",
            "current_outstanding_balance",
            "avg_bill_amount",
            "total_paid",
            "payment_ratio",
            "num_late_payments",
            "avg_delay",
            "max_delay",
            "recent_delay",
            "credit_utilization"
        ]

        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing field: {field}"}), 400

        features = np.array([[
            float(data["credit_limit"]),
            float(data["current_outstanding_balance"]),
            float(data["avg_bill_amount"]),
            float(data["total_paid"]),
            float(data["payment_ratio"]),
            float(data["num_late_payments"]),
            float(data["avg_delay"]),
            float(data["max_delay"]),
            float(data["recent_delay"]),
            float(data["credit_utilization"])
        ]])

        prob = credit_model.predict_proba(features)[0][1]

        threshold = float(data.get("threshold", 0.5))
        pred = int(prob >= threshold)

        return jsonify({
            "risk": "High" if pred == 1 else "Low",
            "probability": round(float(prob), 4),
            "confidence": round(prob * 100, 2),
            "threshold_used": threshold
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# demand forecast (1 day)
@app.route("/predict/forecast", methods=["POST"])
def predict_forecast():
    try:
        data = request.json

        if not data:
            return jsonify({"error": "No input data"}), 400

        features = pd.DataFrame([{
            "family": data["family"],
            "store_nbr": data["store_nbr"],
            "onpromotion": data["onpromotion"],
            "day_of_week": data["day_of_week"],
            "month": data["month"],
            "day_of_month": data["day_of_month"],
            "is_weekend": data["is_weekend"],
            "lag_1": data["lag_1"],
            "lag_7": data["lag_7"],
            "lag_14": data["lag_14"],
            "rolling_mean_7": data["rolling_mean_7"]
        }])

        pred_log = forecast_model.predict(features)[0]
        prediction = np.expm1(pred_log)

        return jsonify({
            "predicted_sales": round(float(prediction), 2)
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# demand forecast (14 days)
@app.route("/predict/forecast/14days", methods=["POST"])
def predict_14_days():
    try:
        data = request.json

        if not data:
            return jsonify({"error": "No input data"}), 400

        predictions = multi_step_forecast(forecast_model, data, days=14)

        return jsonify({
            "forecast_14_days": predictions
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)