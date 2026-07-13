## Building the agents for the Dashboard

Commit 1

Completed on making the modules for 
- CPU 
- Disk 
- Docker
- Ram 
- Temp 


Commit 2

- Added new module to the action section 
- started using the Docker SDK 
- Changed the old collecter form the subprocess using to the Docker SDK

Commit 3

 - Added the new modules like system management and docker management
 - Connected the backend to the basic frontend that is created
 - Added authentication for the login page 
 - Added login page 
 - Added Dasbord Page and only 2 features are there Don't know if its visble 
 - Made an script to start both the frontend and the backend at the same time 
 - Updated the gitignore
 - Added setup script to add admin password and username for the website
 
Commit 4 

 - Connected the Proc with the the frontend and displays Data
 - Added new agents file that take all the collecters information and display in the frontend
 - Added Requirements.txt for downloading all the dep
 - New Python script to install all the backend and frontend dep in one click
 - Connected the ports.py to the route and also made an frontend to see the data 
 - Changed the ports fuction to only show Local Address ports and process 
 
Commit 5 

 - Made an new collector cloudflared.py and it conatins functions to check the yml. 
 - can check all the things hosted on server. 
 - can preview websites using the preview using iframe. 

Commit 6 

 - Docker file for frontend to work
 - New run.py to run the backend alone
 - Changed to the port 8001

Commit 7 

 - Backend env creating if not existing and npm also for install.py
 - Changed the docker file and removed public folder which was empty