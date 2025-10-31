import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import classification_report, accuracy_score
from sklearn.preprocessing import StandardScaler
import joblib

# Load your data
df = pd.read_csv('all_hrv_data3.csv', sep=';')
df['RMSSD'] = pd.to_numeric(df['RMSSD'], errors='coerce')
df = df.dropna()

print(f"Dataset shape: {df.shape}")
print(f"Label distribution:\n{df['label'].value_counts()}")

# Select features - using only the most important ones
feature_columns = ['HR', 'RMSSD']

X = df[feature_columns]
y = df['label']

print(f"Using {len(feature_columns)} features: {feature_columns}")

# Split data
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.3, random_state=42, stratify=y
)

# Scale features
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

print("\nTraining Model (Random Forest)...")

# Use Random Forest
model = RandomForestClassifier(
    n_estimators=200,
    max_depth=10,
    min_samples_split=5,
    min_samples_leaf=3,
    random_state=42,
    class_weight='balanced'
)

# Cross-validation
cv_scores = cross_val_score(model, X_train_scaled, y_train, cv=5)
print(f"Cross-validation mean: {cv_scores.mean():.3f}")

# Train the model
model.fit(X_train_scaled, y_train)

# Make predictions
y_pred = model.predict(X_test_scaled)

# Evaluate
accuracy = accuracy_score(y_test, y_pred)
print(f"\nModel Accuracy: {accuracy:.3f}")

print("\nClassification Report:")
print(classification_report(
    y_test, y_pred,
    target_names=['no stress', 'stress']
))

# Feature importance
feature_importance = pd.DataFrame({
    'feature': feature_columns,
    'importance': model.feature_importances_
}).sort_values('importance', ascending=False)

print("\nFeature Importance:")
print(feature_importance)

# Plot feature importance
plt.figure(figsize=(10, 6))
sns.barplot(data=feature_importance, x='importance', y='feature')
plt.title('Feature Importance for Stress Prediction')
plt.tight_layout()
plt.show()

# Save the model and scaler
joblib.dump(model, 'improved_stress_model.pkl')
joblib.dump(scaler, 'scaler.pkl')
print("\nModel saved as 'improved_stress_model.pkl'")
