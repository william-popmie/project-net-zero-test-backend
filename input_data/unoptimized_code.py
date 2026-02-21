"""
train.py — Minimal Linear Regression trained with Gradient Descent

No libraries. Trains a model: y = w*x + b to fit a straight line.
The "stupid" dataset: y = 3x + 2 with a bit of noise.

Run:  python train.py
Test: pytest test_train.py
"""

import random
import math


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

def generate_data(n: int = 50, seed: int = 42) -> list[tuple[float, float]]:
    """Generate noisy samples from y = 3x + 2."""
    random.seed(seed)
    data = []
    for i in range(n):
        x = i / n
        noise = random.uniform(-0.1, 0.1)
        y = 3 * x + 2 + noise
        data.append((x, y))
    return data


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def predict(x: float, w: float, b: float) -> float:
    return w * x + b


def mse_loss(data: list[tuple[float, float]], w: float, b: float) -> float:
    """Mean Squared Error loss."""
    total = 0.0
    for x, y in data:
        error = predict(x, w, b) - y
        total += error ** 2
    return total / len(data)


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def compute_gradients(
    data: list[tuple[float, float]], w: float, b: float
) -> tuple[float, float]:
    """Compute dL/dw and dL/db via backprop (closed-form for MSE)."""
    n = len(data)
    dw = 0.0
    db = 0.0
    for x, y in data:
        error = predict(x, w, b) - y
        dw += (2 / n) * error * x
        db += (2 / n) * error
    return dw, db


def train(
    data: list[tuple[float, float]],
    lr: float = 0.5,
    epochs: int = 200,
    w_init: float = 0.0,
    b_init: float = 0.0,
) -> dict:
    """
    Gradient descent training loop.

    Returns:
        w, b      — learned parameters
        losses    — loss per epoch
        epochs    — number of epochs run
    """
    w, b = w_init, b_init
    losses = []

    for epoch in range(epochs):
        loss = mse_loss(data, w, b)
        losses.append(loss)

        dw, db = compute_gradients(data, w, b)
        w -= lr * dw
        b -= lr * db

        if (epoch + 1) % 50 == 0:
            print(f"  Epoch {epoch + 1:>4} | Loss: {loss:.6f} | w={w:.4f}, b={b:.4f}")

    return {"w": w, "b": b, "losses": losses, "epochs": epochs}


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate(data: list[tuple[float, float]], w: float, b: float) -> dict:
    """Returns MSE and mean absolute error on the dataset."""
    mse = mse_loss(data, w, b)
    mae = sum(abs(predict(x, w, b) - y) for x, y in data) / len(data)
    return {"mse": mse, "mae": mae}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("🧠  Training linear model on y = 3x + 2\n")

    data = generate_data(n=50)

    print("Before training:")
    print(f"  Loss: {mse_loss(data, 0.0, 0.0):.4f}\n")

    result = train(data, lr=0.5, epochs=200)

    w, b = result["w"], result["b"]
    metrics = evaluate(data, w, b)

    print(f"\nAfter training:")
    print(f"  w = {w:.4f}  (target ~3.0)")
    print(f"  b = {b:.4f}  (target ~2.0)")
    print(f"  MSE: {metrics['mse']:.6f}")
    print(f"  MAE: {metrics['mae']:.6f}")