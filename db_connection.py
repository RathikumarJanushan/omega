import cv2

# URL of the IP webcam video stream
url = "http://192.168.8.171:8080/video"

# Open a connection to the video stream
cap = cv2.VideoCapture(url)

# Check if the connection is successfully opened
if not cap.isOpened():
    print("Error: Could not open video stream.")
    exit()

# Loop to continuously get frames
while True:
    # Capture frame-by-frame
    ret, frame = cap.read()

    # If the frame was not retrieved correctly, break the loop
    if not ret:
        print("Error: Failed to retrieve frame.")
        break

    # Display the resulting frame
    cv2.imshow('IP Webcam Stream', frame)

    # Break the loop when 'q' key is pressed
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# When everything is done, release the capture and close the windows
cap.release()
cv2.destroyAllWindows()
