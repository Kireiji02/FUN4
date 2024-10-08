#!/usr/bin/python3

import rclpy
import numpy as np
from math import pi
from spatialmath import SE3
from rclpy.node import Node
import roboticstoolbox as rtb
from fun4.srv import ModeSelector
from sensor_msgs.msg import JointState
from tf2_ros import TransformListener, Buffer
from geometry_msgs.msg import PoseStamped, Twist

robot = rtb.DHRobot(
        [   
        rtb.RevoluteMDH(a=0.0,       alpha=0.0,     offset=0.0,     d=0.2   ),
        rtb.RevoluteMDH(a=0.0,       alpha=pi/2,    offset=0.0,     d=0.02  ),
        rtb.RevoluteMDH(a=0.25,      alpha=0.0,     offset=0.0,     d=0.0  )
        ], tool=SE3.Tx(0.28),
        name="RRR_Robot"
    )

class PoseAnalyzerNode(Node):
    def __init__(self):
        super().__init__('pose_analyzer_node')
        
        #----------------------------Variables----------------------------#
        
        self.rand = [0.0,0.0,0.0]
        self.q_initial = [0.0, 0.0, 1.4]
        self.q_velocities = JointState() 
        self.q_velocities.velocity = [0.0,0.0,0.0]
        self.q_position = JointState()
        self.q_position.position = [0.0,0.0,0.0]
        self.q_position.name = ["joint_1", "joint_2", "joint_3"]
        self.service = False
        self.mode = 0
        self.Kp = 1.2
        self.initiate = False
        self.linear_velocity = [0.0,0.0,0.0]
        
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.target_frame = "end_effector"
        self.source_frame = "link_0"
        self.position = np.array([0.0, 0.0, 0.0])
        self.orientation = [0.0, 0.0, 0.0]
        
        self.target_position = np.array([0.0, 0.0, 0.0])
        
        #----------------------------Timer----------------------------#
        
        self.declare_parameter('frequency', 100.0)   
        self.frequency = self.get_parameter('frequency').get_parameter_value().double_value
        
        self.create_timer(1/self.frequency, self.timer_callback)
        
        #----------------------------Topic_Publishers----------------------------#
        
        self.joint_state_pub = self.create_publisher(JointState, '/joint_states', 10)
        
        #----------------------------Topic_Subscribers----------------------------#
        
        self.create_subscription(PoseStamped, '/target', self.callback_randomizer, 10)
        self.create_subscription(Twist, '/cmd_vel', self.cmd_vel_callback, 10)
        
        #----------------------------Service_Servers----------------------------#
        
        self.inverse_and_mode_server = self.create_service(ModeSelector, '/mode_select', self.callback_inverse)
        
        #----------------------------Service_Clients----------------------------#
        
    def timer_callback(self):
        
        print(f'{self.linear_velocity[0]}')

        if self.service:
            
            self.get_transform()
            
            error = self.target_position - self.position
            
            if self.mode == 1 or self.mode == 3:
                v = self.Kp *error
            
            elif self.mode == 2:
                v = self.linear_velocity
            
            J_full = robot.jacob0(self.q_initial)
            J = J_full[:3, :]
            
            lambda_ = 0.01
            J_pseudo_inv = np.linalg.inv(J.T @ J + lambda_ * np.eye(J.shape[1])) @ J.T
            q_dot = J_pseudo_inv @ v

            self.q_velocities.velocity = [q_dot[0], q_dot[1], q_dot[2]]
            
            self.q_initial = self.q_initial + q_dot * 1/self.frequency
            
            if np.linalg.norm(error) < 1e-3:
                
                self.get_logger().info(f"Finish at x: {self.position[0]}, y: {self.position[1]}, z: {self.position[2]}")
                self.q_velocities.velocity = [0.0, 0.0, 0.0]
                
                self.service = False
                
                if self.mode == 3:
                    self.target_position = [self.rand[0],self.rand[1],self.rand[2]]
                    self.service = True
                    
            self.jointstate(self.q_velocities.velocity)

    def cmd_vel_callback(self, msg: Twist):
        self.linear_velocity = np.array([msg.linear.x, msg.linear.y, msg.linear.z])
        
    def get_transform(self):
        try:
            now = rclpy.time.Time()
            transform = self.tf_buffer.lookup_transform(
                self.source_frame,   
                self.target_frame,   
                now)
            position = transform.transform.translation
            
            self.position[0] = position.x
            self.position[1] = position.y
            self.position[2] = position.z
        
        except Exception as e:
            self.get_logger().error(f"Failed to get transform: {e}")
        
    def callback_inverse(self, request:ModeSelector.Request , response:ModeSelector.Response):
        self.service = True
        
        if (request.mode.data == 1):
            self.target_position = [request.ipk_target.position.x,request.ipk_target.position.y,request.ipk_target.position.z]
        
        elif (request.mode.data == 3):
            self.target_position = [self.rand[0],self.rand[1],self.rand[2]]
            
        self.mode = request.mode.data   
  
        self.get_logger().error(f"{self.target_position}")
        response.state.data = True
        response.mode.data = request.mode.data

        return response
    
    def jointstate(self, q):
        self.q_position.header.stamp = self.get_clock().now().to_msg()
        
        for i in range(len(q)):
        
            self.q_position.position[i] += q[i] * 1/self.frequency
            self.q_position.position[i] %= 2*pi
        self.joint_state_pub.publish(self.q_position)
        
    def callback_randomizer(self, msg):
        self.rand[0] = msg.pose.position.x
        self.rand[1] = msg.pose.position.y
        self.rand[2] = msg.pose.position.z

def main(args=None):
    rclpy.init(args=args)
    node = PoseAnalyzerNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
