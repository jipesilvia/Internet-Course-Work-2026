#!/usr/bin/python
# -*- coding: utf-8 -*-
 
# The modules required
import sys
import socket
import struct
import os

'''
Created on top of the template. 
Requires all extrafeatures at the same time.

''' 

LOCAL_IP = "localhost"


# UDP - STRUCTURE
# Class that handles the protocol that works on top of udp.
# This works 
class UDPS:

    UDP_MESSAGE_MAX_SIZE = 142
    STRUCT_FORMAT = '!8s??HH128s'
    parity_check_failed = False

    # Main init
    def __init__(self, cid, content_length, content, ack=True, eom=False, data_remaining=0):
        self.cid = cid
        self.ack = ack
        self.eom = eom
        self.data_remaining = data_remaining
        self.content_length = content_length
        self.content = content
        type(self).parity_check_failed = False

    # Initializes object based on a string.
    @classmethod
    def from_content(cls, cid, content):
        content_length = len(content)
        return cls(cid=cid, content_length=content_length, content=content)
    
    # Initializes object from binary data.
    @classmethod
    def from_data(cls, data):
        cid, ack, eom, data_remaining, content_length, content = struct.unpack(cls.STRUCT_FORMAT, data)
        return cls(cid=cid.decode(), content_length=content_length, content=content.decode()[0:content_length],
                    ack=ack, eom=eom, data_remaining=data_remaining)
    
    # Initializes object based on message received through the socket which is defined.
    # Handles multipart
    # Decrypts
    # Handles paritybits
    # This is somewhat stupid way of doing this
    @classmethod
    def from_socket(cls, socket, my_keys, server_keys, ack_dest, cid):

        received_message = socket.recv(cls.UDP_MESSAGE_MAX_SIZE)
        udps_recv = UDPS.from_data(received_message)
        # Exit program if eom bit is set!
        if udps_recv.eom == True:
            print("[SERVER]: {}".format(udps_recv.content))
            sys.exit()

        if udps_recv.__check_and_remove_parity_bits():
            cls.parity_check_failed = True

        if len(server_keys) > 0:
            udps_recv.__decrypt_content_with_key(server_keys.pop(0))
        
        if udps_recv.data_remaining > 0:
            while True:
                next_message = socket.recv(cls.UDP_MESSAGE_MAX_SIZE)
                udps_nextpart = UDPS.from_data(next_message)

                if udps_nextpart.__check_and_remove_parity_bits():
                    cls.parity_check_failed = True

                if len(server_keys) > 0:
                    udps_nextpart.__decrypt_content_with_key(server_keys.pop(0))
                
                udps_recv.content += udps_nextpart.content
                udps_recv.content_length += udps_nextpart.content_length

                if udps_nextpart.data_remaining <= 0:
                    break
        
        # Answer with "Send again" if parity check fails.
        # Recursively create new objects with from_socket() until no errors.
        if cls.parity_check_failed:
            print("[SERVER]: !!Message contained errors!!\n")
            send_again = UDPS.from_content(cid, "Send again")
            send_again.ack = False
            send_again.send_message_to(socket=socket, dest=ack_dest, keys=my_keys)

            udps_recv = UDPS.from_socket(socket=socket, my_keys=my_keys, server_keys=server_keys, 
                                         ack_dest=ack_dest, cid=cid)

        return cls(cid=udps_recv.cid, content_length=udps_recv.content_length, content=udps_recv.content,
                    ack=udps_recv.ack, eom=udps_recv.eom, data_remaining=udps_recv.data_remaining)
    
    # Returns a bytes object that follwos this protocol.
    def __conver_to_bits(self):
        bits = struct.pack(self.STRUCT_FORMAT, self.cid.encode(), self.ack, self.eom, 
                           self.data_remaining, self.content_length, self.content.encode())
        return bits
    
    # Encrypts content
    def __encrypt_content_with_key(self, key):
        encrypted_message = []
        for i in range(self.content_length):
            char = chr(ord(self.content[i]) ^ ord(key[i]))
            encrypted_message.append(char)   
        self.content = "".join(encrypted_message)

    # Decrypts content
    def __decrypt_content_with_key(self, key):
        decrypted_message = []
        for i in range(self.content_length):
            char = chr(ord(self.content[i]) ^ ord(key[i]))
            decrypted_message.append(char)
        self.content = "".join(decrypted_message)

    # Adds parity bit to every character in content
    def __add_parity_bits(self):
        content = []
        for i in range(self.content_length):
            char = ord(self.content[i])
            char <<= 1
            char += self.__get_parity(char)
            content.append(chr(char))
        self.content = "".join(content)

    
    # Return True if parity does not match.
    def __check_and_remove_parity_bits(self):
        content = []

        if self.parity_check_failed:
            return True
        
        for i in range(self.content_length):
            char = ord(self.content[i])
            parity_bit = 1 & char
            char >>= 1 
            actual_parity = self.__get_parity(char)

            if parity_bit == actual_parity:
                content.append(chr(char))
                continue

            return True
        
        self.content = "".join(content)
        return False    
    
    # Copied from the instructions example!
    # Returns the parity of char
    def __get_parity(self, char):
        while char > 1:
            char = (char >> 1) ^ (char & 1)
        return char
    
    # Sends message/content to the defined socket
    # Uses multipart when needed
    # Encrypts
    # Adds parity bits
    def send_message_to(self, socket, dest, keys):
        
        print("[CLIENT]: {}\n".format(self.content))

        while True:

            if self.content_length > 64:
                udps_piece = UDPS.from_content(self.cid, self.content[0:64])
                self.content = self.content[64:self.content_length]
                self.content_length -= udps_piece.content_length
                udps_piece.data_remaining = self.content_length
                if len(keys) > 0:
                    udps_piece.__encrypt_content_with_key(keys.pop(0))

                udps_piece.__add_parity_bits()

                socket.sendto(udps_piece.__conver_to_bits(), dest)
                continue
            
            if len(keys) > 0:
                self.__encrypt_content_with_key(keys.pop(0))
            
            self.__add_parity_bits()

            socket.sendto(self.__conver_to_bits(), dest)
            break


def send_and_receive_tcp(address, port, message):
    print("You gave arguments: {} {} {}\n".format(address, port, message))
    # create TCP socket
    tcp_socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM)
    # connect socket to given address and port
    tcp_socket.connect((address, port))
    # python3 sendall() requires bytes like object. encode the message with str.encode() command
    m = (message + "\r\n").encode()
    # send given message to socket
    tcp_socket.sendall(m)

    print("[CLIENT]: {}\n".format(message))

    my_keys = []
    server_keys = []

    for i in range(20):
        my_key = generate_encryption_key() + "\r\n"
        print("[CLIENT]: {}".format(my_key))
        my_keys.append(my_key)
        tcp_socket.sendall(my_key.encode())

    print("[CLIENT]: {}".format(".\r\n"))
    tcp_socket.sendall(".\r\n".encode())

    received_message = tcp_socket.recv(1400).decode()
    print("[SERVER]: {}\n".format(received_message))
    split_message = received_message.split("\r\n")

    first_part = split_message.pop(0)

    split_first_part = first_part.split()
    cid = str(split_first_part[1])
    udp_port = int(split_first_part[2])


    for key in split_message:
        if len(key) == 64:
            server_keys.append(key)
        if key == ".":
            break


    tcp_socket.close()

    send_and_receive_udp(address, udp_port, cid, my_keys, server_keys)
    return
 

def generate_encryption_key(length=32):
    key = os.urandom(length).hex()
    return key


def send_and_receive_udp(address, port, cid, my_keys, server_keys):
    destAnP = (address, port)
    first_message = "Hello from {}\n".format(cid)
    udps_first = UDPS.from_content(cid, first_message)
    udp_socket = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
    udps_first.send_message_to(udp_socket, destAnP, my_keys)

    while True:
        
        udps_recv = UDPS.from_socket(udp_socket,my_keys, server_keys, destAnP, cid)
        
        print("[SERVER]: {}\n".format(udps_recv.content))

        content_reversed = get_reverse_order(udps_recv.content)
        
        udps_depar = UDPS.from_content(cid, content_reversed)
        udps_depar.send_message_to(udp_socket, destAnP, my_keys)
 
def get_reverse_order(content):
    words = content.split()
    words.reverse()
    new_content = " ".join(words)
    return new_content

def main():
    USAGE = 'usage: %s <server address> <server port> <message>' % sys.argv[0]
 
    try:
        # Get the server address, port and message from command line arguments
        server_address = str(sys.argv[1])
        server_tcpport = int(sys.argv[2])
        message = str(sys.argv[3])
    except IndexError:
        print("Index Error")
    except ValueError:
        print("Value Error")
    # Print usage instructions and exit if we didn't get proper arguments
        sys.exit(USAGE)
 
    send_and_receive_tcp(server_address, server_tcpport, message)
 
 
if __name__ == '__main__':
    # Call the main function when this script is executed
    main()
