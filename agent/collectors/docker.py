import subprocess 

def docker():
    dockerout = subprocess.run(['docker', 'ps'], capture_output=True, text=True)
    print(dockerout.stdout)