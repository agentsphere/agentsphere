import asyncio
import subprocess
import os
import pty
import shlex
import stat
import websockets
import select
from dotenv import load_dotenv
load_dotenv(dotenv_path='./client/.env')

TOKEN = os.getenv("TOKEN")
WSS_SERVER = os.getenv("WSS_URL")

print(TOKEN)
print(WSS_SERVER)


def clean_terminal_output(raw: str) -> str:
    """Process raw subprocess output with terminal control characters into cleaned text."""
    output_lines = []
    current_line = []      # buffer for characters in the current line
    cursor_pos = 0         # current cursor position in the line

    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch == '\r':
            # Carriage return: move cursor to line start
            cursor_pos = 0
        elif ch == '\n':
            # Newline: end the current line and reset cursor for a new line
            output_lines.append(''.join(current_line))
            current_line = []
            cursor_pos = 0
        elif ch == '\b':
            # Backspace: move cursor one position left (do not delete char yet)
            if cursor_pos > 0:
                cursor_pos -= 1
        elif ch == '\t':
            # Tab: move cursor to next 8-character tab stop
            next_tab = (cursor_pos // 8 + 1) * 8
            # Extend line with spaces if needed to reach the next tab stop
            if next_tab > len(current_line):
                current_line.extend(' ' * (next_tab - len(current_line)))
            cursor_pos = next_tab
        elif ch == '\x1b':
            # Start of an ANSI escape sequence
            if i + 1 < len(raw) and raw[i+1] == '[':
                # Find the end of the CSI sequence (ends with a letter or @,`, etc.)
                j = i + 2
                while j < len(raw) and not (0x40 <= ord(raw[j]) <= 0x7E):
                    j += 1
                if j >= len(raw):
                    break  # malformed sequence (end not found)
                seq = raw[i:j+1]            # e.g. "\x1b[2K"
                final_char = raw[j]         # the command letter, e.g. 'K'
                params = seq[2:-1]          # the content between '[' and the final char
                # Handle a few specific ANSI CSI codes:
                if final_char == 'K':  # Erase In Line
                    if params == '' or params == '0':
                        # Erase from cursor to end of line
                        if cursor_pos < len(current_line):
                            current_line = current_line[:cursor_pos]
                    elif params == '1':
                        # Erase from start of line to cursor (inclusive)
                        if cursor_pos > len(current_line):
                            # if cursor is beyond current content, extend with spaces
                            current_line.extend(' ' * (cursor_pos - len(current_line)))
                        # Replace all chars up to cursor position with spaces
                        for idx in range(0, min(cursor_pos, len(current_line))):
                            current_line[idx] = ' '
                    elif params == '2':
                        # Erase entire line
                        if cursor_pos > len(current_line):
                            current_line.extend(' ' * (cursor_pos - len(current_line)))
                        # Clear the line buffer completely
                        current_line = []
                elif final_char == 'J':  # Erase Screen
                    if params == '' or params == '0':
                        # Erase from cursor to end of screen (here, to end of line and beyond)
                        if cursor_pos < len(current_line):
                            current_line = current_line[:cursor_pos]
                        # (No other lines below to clear in this linear output)
                    elif params == '1':
                        # Erase from start of screen to cursor
                        if cursor_pos > len(current_line):
                            current_line.extend(' ' * (cursor_pos - len(current_line)))
                        for idx in range(0, min(cursor_pos, len(current_line))):
                            current_line[idx] = ' '
                        # Also clear all previous lines (they would disappear from screen)
                        output_lines = ['' for _ in output_lines]
                    elif params == '2':
                        # Erase entire screen: clear all stored lines and current line
                        output_lines = []
                        current_line = []
                        cursor_pos = 0
                elif final_char == 'm':
                    # SGR (text color/style) - no visible text effect, ignore
                    pass
                # ... (You could handle other cases like cursor movements if needed)
                # Skip past the entire escape sequence
                i = j
            # If it's not a CSI sequence (ESC [), just ignore this ESC.
        else:
            # Regular character output
            if cursor_pos > len(current_line):
                # If cursor moved beyond current content (e.g., via spaces), pad with spaces
                current_line.extend(' ' * (cursor_pos - len(current_line)))
            if cursor_pos < len(current_line):
                # Overwrite character at the current cursor position
                current_line[cursor_pos] = ch
            else:
                # Append character at end of line
                current_line.append(ch)
            cursor_pos += 1
        i += 1

    # If the raw output didn't end with a newline, append the last line buffer
    if current_line:
        output_lines.append(''.join(current_line))
    elif len(raw) > 0 and raw[-1] == '\n':
        # If it ended with a newline, add an empty line to signify that break
        output_lines.append('')

    # Join lines with newline characters to form the final string
    return '\n'.join(output_lines)

def run_command(command):
    master_fd, slave_fd = pty.openpty()

    # Start the process in a subprocess with the slave end of the pty
    proc = subprocess.Popen(
        command,
        shell=True,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
        universal_newlines=True,
    )

    os.close(slave_fd)  # No need for the parent to keep the slave end open

    output = ""
    print("start")
    while True:
        rlist, _, _ = select.select([master_fd], [], [], 0.1)
        if rlist:
            try:
                l = os.read(master_fd, 1024).decode()
                if not l:
                    break
                #print(repr(data))
                output += l
            except OSError:
                break
        if proc.poll() is not None:
            # Wait for any final output after process ends
            while True:
                try:
                    l = os.read(master_fd, 1024).decode()
                    if not l:
                        break
                    output += l
                except OSError:
                    break
            break
    print("end")

    os.close(master_fd)
    proc.wait()

    return output, proc.returncode
    

def split_command(command_str):
    return shlex.split(command_str)

def strip_surrounding_quotes(cmd: str) -> str:
    if len(cmd) >= 2 and cmd[0] == cmd[-1] and cmd[0] in ("'", '"'):
        return cmd[1:-1]
    return cmd

async def receive_file():

    uri = f"{WSS_SERVER}?token={TOKEN}"

    while True:
        try:
            async with websockets.connect(uri) as websocket:

                while True:
                    print("Connected to server. Awaiting instructions...")

                    # Receive filename
                    execution_type = await websocket.recv()
                    if execution_type == "COMMAND":
                        try: 
                            command = await websocket.recv()
                            print(f"getting command {command}")
                            command = strip_surrounding_quotes(command)

                            print(f"command {command}")

                            out = []
                            for c in command.split("&&"):
                                    # Check if the command starts with './'

                                split = split_command(c)
                                if c.startswith("./"):
                                    # Extract the file name after './'
                                    file_name = split[0]
                                    rightmost_part = file_name.split("/")[-1]  # Get the last part after the last '/'


                                    # Check if the file exists in the current directory
                                    if not os.path.isfile(file_name):
                                        print(f"File '{file_name}' does not exist. Removing './' prefix.")
                                        split[0] = rightmost_part  # Remove './' prefix


                                #print(f"c {c}")
                                out.append(f"{c}")



                                status = 0

                                if "cd" == split[0]:
                                    os.chdir(split[1])
                                    print(f"cd {split[1]}")
                                    out.append(f"currentDir: {os.getcwd()}")
                                elif "pwd" in split[0]:
                                    print(f"pwd {os.getcwd()}")
                                    out.append(f"currentDir: {os.getcwd()}")
                                else:
                                    o, st = run_command(c)
                                    cout = clean_terminal_output(o)
                                    status = st
                                    out.append(cout)
                            print(f"status {status}, terminal output: {out}")
                        
                            await websocket.send(f"status {status}, terminal output: {out}") 
                        except Exception as e:  
                            print(f"Error executing command: {e}")
                            await websocket.send(f"Error executing command: {e}")

                    elif execution_type == "FILE":
                        filename = await websocket.recv()
                        print(f"Receiving file: {filename}")


                        # Receive file content in chunks
                        with open(f"received_{filename}", "wb") as f:
                            while True:
                                chunk = await websocket.recv()
                                if chunk == b"EOF":  # End of file signal
                                    break
                                f.write(chunk)

                        print(f"File {filename} received and saved as received_{filename}")

                        # Set file as executable
                        st = os.stat(f"received_{filename}")
                        os.chmod(f"received_{filename}", st.st_mode | stat.S_IEXEC)

                        # Run the received file
                        process = await asyncio.create_subprocess_exec(
                            f"./received_{filename}",
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE
                        )

                        stdout, stderr = await process.communicate()

                        # Send acknowledgment
                        await websocket.send(f"Process Output:\nReturn Code: {process.returncode}\nError: {stderr.decode()}\nOutput: {stdout.decode()}")

        except websockets.exceptions.ConnectionClosedError:
            print("Connection lost. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)  # Wait before reconnecting
        except Exception as e:
            print(f"Unexpected error: {e}")
            await asyncio.sleep(5)  # Avoid spamming reconnections

async def main():
    await receive_file()

# Run the event loop
asyncio.run(main())
