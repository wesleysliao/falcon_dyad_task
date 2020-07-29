#!/usr/bin/env python3

import argparse
import traceback

import socket
import struct
import pygame
import pygame.gfxdraw

import ctypes
ctypes.cdll.LoadLibrary("falcon_c/lib/falcon_c.so")
falcon_c = ctypes.CDLL("falcon_c/lib/falcon_c.so")

falcon_get_x = falcon_c.falcon_get_pos_x
falcon_get_x.restype = ctypes.c_double

falcon_get_y = falcon_c.falcon_get_pos_y
falcon_get_y.restype = ctypes.c_double

falcon_get_z = falcon_c.falcon_get_pos_z
falcon_get_z.restype = ctypes.c_double


class FalconDyadApp:

    def __init__(self, is_client, ip_addr, port, falcon_device_num):
        self.is_client = is_client
        self.is_host = not is_client
        self.socket_ip = ip_addr
        self.socket_port = port

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client = None
        self.client_ip = None

        self.data_format = "ff"
        self.data_bytes = struct.calcsize(self.data_format)

        self.cursor_host = pygame.Vector2(0.0, 0.0)
        self.cursor_client = pygame.Vector2(0.0, 0.0)


        if(falcon_device_num < 0):
            if(is_client):
                self.falcon_ref = falcon_c.falcon_init(1)
            else:
                self.falcon_ref = falcon_c.falcon_init(0)
        else:
            self.falcon_ref = falcon_c.falcon_init(falcon_device_num)

        falcon_c.falcon_load_firmware(self.falcon_ref, "falcon_c/firmware/test_firmware.bin")

        if(self.is_client):
            falcon_c.falcon_set_leds(self.falcon_ref, ctypes.c_bool(False), ctypes.c_bool(False), ctypes.c_bool(True))
        else:
            falcon_c.falcon_set_leds(self.falcon_ref, ctypes.c_bool(True), ctypes.c_bool(False), ctypes.c_bool(False))

        pygame.init()
        pygame.mouse.set_visible(False)

        self.target_fps = 120.0
        self.clock = pygame.time.Clock()

        self.screen_width = 640
        self.screen_height = 640
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))

        self.screen_center_x = self.screen_width / 2
        self.screen_center_y = self.screen_width / 2

        if(is_client):
            pygame.display.set_caption("Dyad Task CLIENT")
        else:
            pygame.display.set_caption("Dyad Task HOST")


        self.workspace_scale = 250
        self.cursor_radius = 40


        self.tasklist = []
        self.current_task = None


    def __del__(self):
        self.disconnect()
        falcon_c.falcon_exit(self.falcon_ref)

    def connect(self):
        if(self.is_client):
            print("Connecting to ", self.socket_ip)
            self.socket.connect((self.socket_ip, self.socket_port))

        else:  #host
            print("Waiting for client to connect")
            self.socket.bind((self.socket_ip, self.socket_port))
            self.socket.listen()

            self.client, self.client_ip = self.socket.accept()
            print("Client connected from ", self.client_ip)

    def disconnect(self):
        print("disconnecting")
        self.socket.shutdown(socket.SHUT_RDWR)
        self.socket.close()

        if(self.is_host):
            self.client.close()


    def send_recv_data(self):
        if(self.is_client):
            data_in = self.socket.recv(self.data_bytes)
            formatted_tuple = struct.unpack(self.data_format, data_in)

            self.cursor_host[0] = formatted_tuple[0]
            self.cursor_host[1] = formatted_tuple[1]

            data_out = struct.pack(self.data_format, self.cursor_client[0], self.cursor_client[1])
            self.socket.sendall(data_out)

        else:
            data_out = struct.pack(self.data_format, self.cursor_host[0], self.cursor_host[1])
            self.client.sendall(data_out)

            data_in = self.client.recv(self.data_bytes)
            formatted_tuple = struct.unpack(self.data_format, data_in)

            self.cursor_client[0] = formatted_tuple[0]
            self.cursor_client[1] = formatted_tuple[1]


    def poll_input(self):

        falcon_c.falcon_run_io_loop(self.falcon_ref)

        falcon_pos = pygame.Vector3(0.0, 0.0, 0.0)
        falcon_pos[0] = falcon_get_x(self.falcon_ref) / 0.05
        falcon_pos[1] = falcon_get_y(self.falcon_ref) / -0.05
        #falcon_pos[2] = falcon_get_z(self.falcon_ref)

        if(self.is_client):
            self.cursor_client = falcon_pos[:2]
        else:
            self.cursor_host = falcon_pos[:2]

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.quit = True

    def update(self, dt_s):

        diff = self.cursor_client - self.cursor_host
        if(diff.length() > 0.0 and (diff.length() * self.workspace_scale) <= (self.cursor_radius * 2)):

            penetration = diff.length() - ((self.cursor_radius * 2) / self.workspace_scale)
            k = 10.0
            if(self.is_host): k *= -1.0
            surface_force = diff.normalize() * penetration * k

            falcon_c.falcon_set_force(self.falcon_ref,
                                    ctypes.c_double(-surface_force[0]),
                                    ctypes.c_double(surface_force[1]),
                                    ctypes.c_double(0.0))

            print("touching")
        else:
            falcon_c.falcon_set_force(self.falcon_ref,
                                       ctypes.c_double(0.0),
                                       ctypes.c_double(0.0),
                                       ctypes.c_double(0.0))



    def draw(self):
        self.screen.fill((0,0,0))

        #draw workspace
        workspace_size = int((self.workspace_scale + self.cursor_radius) * 2)
        workspace_x = int((self.screen_width - workspace_size) / 2)
        workspace_y = int((self.screen_height - workspace_size) / 2)
        pygame.draw.rect(self.screen, (20,20,20), pygame.Rect(workspace_x, workspace_y, workspace_size, workspace_size))


        #draw cursors
        pygame.gfxdraw.filled_circle(self.screen,
                           int((self.cursor_client[0] * self.workspace_scale) + self.screen_center_x),
                            int((self.cursor_client[1] * self.workspace_scale) + self.screen_center_y),
                                     self.cursor_radius, (0,0,255,127))

        pygame.gfxdraw.filled_circle(self.screen,
                           int((self.cursor_host[0] * self.workspace_scale) + self.screen_center_x),
                            int((self.cursor_host[1] * self.workspace_scale) + self.screen_center_y),
                                     self.cursor_radius, (255,0,0,127))

        pygame.display.flip()



    def loop(self):

        self.quit = False

        while not self.quit:
            self.clock.tick(self.target_fps)
            dt_s = self.clock.get_time() / 1000.0

            self.send_recv_data()

            self.poll_input()

            self.update(dt_s)

            self.draw()





if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Falcon Dyad Program')
    parser.add_argument("-c", "--client", action="store_true", help="act as client, connect to host")
    parser.add_argument("-i", "--ip", metavar="IP", default="127.0.0.1", help="set socket IP (defaults to 127.0.0.1)")
    parser.add_argument("-p", "--port", metavar="PORT", type=int, default=65432, help="set socket port (defaults to 65432)")
    parser.add_argument("-d", "--device", metavar="N", type=int, default=-1, help="set Novint Falcon device number (defaults 0 for host, 1 for client)")

    args = parser.parse_args()
    app = FalconDyadApp(args.client, args.ip, args.port, args.device)

    app.connect()
    app.loop()
