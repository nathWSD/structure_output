import subprocess
import sys
import time
import socket
import os

def is_port_in_use(port, host="127.0.0.1"):
    """Check if the target port is already occupied."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0

def main():
    mlflow_port = 8050
    
    # 1. Start the MLflow Server if it is not already running
    if not is_port_in_use(mlflow_port):
        print(f"Starting MLflow server on port {mlflow_port}...")
        
        # Use sys.executable to run mlflow within the current active virtual environment
        mlflow_command = [
            sys.executable, "-m", "mlflow", "server",
            "--backend-store-uri", "sqlite:///mlflow.db",
            "--host", "0.0.0.0", #"127.0.0.1",
            "--port", str(mlflow_port)
        ]
        
        # Spawn MLflow as a background subprocess
        subprocess.Popen(
            mlflow_command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )
        
        # Give the MLflow database/server a brief moment to initialize
        time.sleep(60)
    else:
        print(f"MLflow server is already running on port {mlflow_port}. Skipping startup.")

    # 2. Launch the Streamlit App
    print("Launching Streamlit Application...")
    try:
        # Run streamlit in the foreground so you can view its logs and stop it with Ctrl+C
        subprocess.run(["streamlit", "run", "app.py"])
    except KeyboardInterrupt:
        print("\nShutting down application...")

if __name__ == "__main__":
    main()