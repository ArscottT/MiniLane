import cv2
import numpy as np
import math
import RPi.GPIO as GPIO

# Motors
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)

motor_1_pin = 40 #FIND PWM PIN
motor_1_1 = 29
motor_1_2 = 31

motor_2_pin = 38 #ABOVE
motor_2_1 = 16
motor_2_2 = 18

default_speed = 1000

# Image
rho = 1
theta = np.pi / 180
min_threshold = 10
minLineLength = 5
maxLineGap = 20

video = cv2.VideoCapture(0)

video.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
video.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)


def convert_to_hsv(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    # cv2.imshow("HSV", hsv)

    return hsv


def detect_edges(frame):
    lower_limit = np.array([90, 120, 0], dtype="uint8")  # lower limit of blue
    upper_limit = np.array([150, 255, 255], dtype="uint8")  # upper limit of blue
    mask = cv2.inRange(hsv, lower_limit, upper_limit)  # filter for colour limits

    edges = cv2.Canny(mask, 50, 100)
    # cv2.imshow("edges", edges)

    return edges


def select_roi(edges):
    height, width = edges.shape
    mask = np.zeros_like(edges)  # empty matrix with same dimensions as frame

    # focus on lower half of screen
    # specify coordinates of 4 points(lower left, upper left, upper right, lower right)
    polygon = np.array([[
        (0, height),
        (0, height/2),
        (width, height/2),
        (width, height),
    ]], np.int32)

    cv2.fillPoly(mask, polygon, 255)  # fill polygon with blue
    cropped_edges = cv2.bitwise_and(edges, mask)
    # cv2.imshow("roi", cropped_edges)

    return cropped_edges


def detect_line_segments(cropped_edges):
    line_segments = cv2.HoughLinesP(cropped_edges, rho, theta, min_threshold,
                                   np.array([]), minLineLength, maxLineGap)

    return line_segments


def make_points(frame, line):
    height, width, _ = frame.shape
    slope, intercept = line
    y1 = height  # bottom of the frame
    y2 = int(y1 / 2)  # make points from middle of the frame down

    if slope == 0:
        slope = 0.1

    x1 = int((y1 - intercept) / slope)
    x2 = int((y2 - intercept) / slope)

    return [[x1, y1, x2, y2]]


def display_lines(frame, lines, line_color=(0, 255, 0), line_width=6):  # line color (B,G,R)
    line_image = np.zeros_like(frame)
    if lines is not None:
        for line in lines:
            for x1, y1, x2, y2 in line:
                cv2.line(line_image, (x1, y1), (x2, y2), line_color, line_width)
    line_image = cv2.addWeighted(frame, 0.8, line_image, 1, 1)

    return line_image


def average_slope_intercept(frame, line_segments):
    lane_lines = []
    if line_segments is None:
        print("no line segment detected")
        return lane_lines
    height, width,_ = frame.shape
    left_fit = []
    right_fit = []
    boundary = 1/3
    left_region_boundary = width * (1 - boundary)
    right_region_boundary = width * boundary
    for line_segment in line_segments:
        for x1, y1, x2, y2 in line_segment:
            if x1 == x2:
                print("skipping vertical lines (slope = infinity)")
                continue
            fit = np.polyfit((x1, x2), (y1, y2), 1)
            slope = (y2 - y1) / (x2 - x1)
            intercept = y1 - (slope * x1)
            if slope < 0:
                if x1 < left_region_boundary and x2 < left_region_boundary:
                    left_fit.append((slope, intercept))
            else:
                if x1 > right_region_boundary and x2 > right_region_boundary:
                    right_fit.append((slope, intercept))
    left_fit_average = np.average(left_fit, axis=0)
    if len(left_fit) > 0:
        lane_lines.append(make_points(frame, left_fit_average))
    right_fit_average = np.average(right_fit, axis=0)
    if len(right_fit) > 0:
        lane_lines.append(make_points(frame, right_fit_average))
    # lane_lines is a 2-D array consisting the coordinates of the right and left lane lines
    # for example: lane_lines = [[x1,y1,x2,y2],[x1,y1,x2,y2]]
    # where the left array is for left lane and the right array is for right lane
    # all coordinate points are in pixels
    return lane_lines


def get_steering_angle(frame, lane_lines):
    height, width, _ = frame.shape
    x_offset, y_offset = 0, 0

    if len(lane_lines) == 2: # if two lane lines are detected
        _, _, left_x2, _ = lane_lines[0][0] # extract left x2 from lane_lines array
        _, _, right_x2, _ = lane_lines[1][0] # extract right x2 from lane_lines array
        mid = int(width / 2)
        x_offset = (left_x2 + right_x2) / 2 - mid
        y_offset = int(height / 2)

    elif len(lane_lines) == 1: # if only one line is detected
        x1, _, x2, _ = lane_lines[0][0]
        x_offset = x2 - x1
        y_offset = int(height / 2)

    elif len(lane_lines) == 0: # if no line is detected
        x_offset = 0
        y_offset = int(height / 2)

    angle_to_mid_radian = math.atan(x_offset / y_offset)
    angle_to_mid_deg = int(angle_to_mid_radian * 180.0 / math.pi)
    steering_angle = angle_to_mid_deg + 90

    return steering_angle


def display_heading_line(frame, steering_angle, line_color=(0, 0, 255), line_width=5):
    heading_image = np.zeros_like(frame)
    height, width, _ = frame.shape
    steering_angle_radian = steering_angle / 180.0 * math.pi
    x1 = int(width / 2)
    y1 = height
    x2 = int(x1 - height / 2 / math.tan(steering_angle_radian))
    y2 = int(height / 2)
    cv2.line(heading_image, (x1, y1), (x2, y2), line_color, line_width)
    heading_image = cv2.addWeighted(frame, 0.8, heading_image, 1, 1)
    cv2.imshow("heading", heading_image)

    return heading_image


if __name__ == '__main__':
    # init
    GPIO.setup(motor_1_pin, GPIO.OUT)
    GPIO.setup(motor_2_pin, GPIO.OUT)
    GPIO.setup(motor_1_1, GPIO.OUT)
    GPIO.setup(motor_1_2, GPIO.OUT)
    GPIO.setup(motor_2_1, GPIO.OUT)
    GPIO.setup(motor_2_2, GPIO.OUT)

    GPIO.output(motor_1_1, True)
    GPIO.output(motor_1_2, False)
    GPIO.output(motor_2_1, False)
    GPIO.output(motor_2_2, True)

    motor_1 = GPIO.PWM(motor_1_pin, 1000)
    motor_1.stop()

    motor_2 = GPIO.PWM(motor_2_pin, 1000)
    motor_2.stop()

    while True:
        # Lane detection
        ret, frame = video.read()
        # frame = cv2.flip(frame,-1) # used to flip the image vertically
        hsv = convert_to_hsv(frame)  # convert to hsv
        edges = detect_edges(hsv)  # detect colour
        roi_edges = select_roi(edges)  # returns only region of interest
        line_segments = detect_line_segments(roi_edges)  # detects lines in roi
        lane_lines = average_slope_intercept(frame, line_segments)
        lane_lines_image = display_lines(frame, lane_lines)
        steering_angle = get_steering_angle(frame, lane_lines)
        heading_image = display_heading_line(lane_lines_image, steering_angle)
        # cv2.imshow('original', frame)

        print(steering_angle);
        # Motors

        if steering_angle == 90:
            motor_1.start(default_speed)
            motor_2.start(default_speed)
        elif steering_angle > 90:
            motor_1.start(default_speed - (steering_angle-90))
            motor_2.start(default_speed)
        elif steering_angle < 90:
            motor_1.start(default_speed)
            motor_2.start(default_speed - steering_angle)

        # Exit key
        key = cv2.waitKey(1)
        if key == 27:
            break

    video.release()
    cv2.destroyAllWindows()
