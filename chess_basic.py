#!/usr/bin/env python3
import tkinter as tk
from tkinter import scrolledtext
import copy
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# LAYOUT CONSTANTS — tweak these to resize the board and UI
# ---------------------------------------------------------------------------
SQUARE_SIZE  = 72               # pixel size of each board square
BOARD_PIXELS = SQUARE_SIZE * 8  # total board width/height (576px at default)
SIDEBAR_W    = 230              # right sidebar width
WINDOW_W     = BOARD_PIXELS + SIDEBAR_W
WINDOW_H     = BOARD_PIXELS + 100  # extra room for bottom bar

# ---------------------------------------------------------------------------
# COLORS — change any hex here to restyle
# ---------------------------------------------------------------------------
COLOR_LIGHT      = "#f0d9b5"   # light squares (cream)
COLOR_DARK       = "#b58863"   # dark squares (brown)
COLOR_HELD       = "#7fc97f"   # hover square highlight when holding a piece
COLOR_LAST_FROM  = "#cdd16e"   # last move: origin square tint (yellow-green)
COLOR_LAST_TO    = "#aaba5a"   # last move: destination square tint (darker green)
COLOR_BG         = "#1e1e1e"   # main window background
COLOR_SIDEBAR    = "#2b2b2b"   # sidebar background
COLOR_TEXT       = "#ffffff"   # general text
COLOR_W_PIECE    = "#ffffff"   # white piece fill
COLOR_B_PIECE    = "#111111"   # black piece fill
COLOR_W_TURN     = "#e8e8e8"   # turn indicator color for white
COLOR_B_TURN     = "#888888"   # turn indicator color for black
COLOR_CLOCK_ACT  = "#00ff88"   # active player clock color (bright green)
COLOR_CLOCK_IDLE = "#555555"   # inactive player clock color (dim)

# ---------------------------------------------------------------------------
# UNICODE CHESS SYMBOLS
# key = "color_piecetype",  value = unicode glyph
# ---------------------------------------------------------------------------
SYMBOLS = {
    "w_K": "♔", "w_Q": "♕", "w_R": "♖", "w_B": "♗", "w_N": "♘", "w_P": "♙",
    "b_K": "♚", "b_Q": "♛", "b_R": "♜", "b_B": "♝", "b_N": "♞", "b_P": "♟",
}

# Order for displaying captured pieces — most valuable first
PIECE_ORDER = ["Q", "R", "B", "N", "P", "K"]

# ---------------------------------------------------------------------------
# STARTING BOARD
# Row 0 = rank 8 (black's back rank), row 7 = rank 1 (white's back rank)
# None = empty square
# ---------------------------------------------------------------------------
def make_starting_board():
    """Return the standard chess starting position as an 8x8 list of Optional[str]."""
    # Type ignore: mypy infers [[None]*8] as List[None] but we intentionally
    # mix None and str — the list holds Optional[str] (None = empty, str = piece code)
    b: list = [[None] * 8 for _ in range(8)]
    b[0] = ["b_R","b_N","b_B","b_Q","b_K","b_B","b_N","b_R"]
    b[1] = ["b_P"] * 8
    b[6] = ["w_P"] * 8
    b[7] = ["w_R","w_N","w_B","w_Q","w_K","w_B","w_N","w_R"]
    return b

# ---------------------------------------------------------------------------
# NOTATION HELPERS
# ---------------------------------------------------------------------------
FILE_LETTERS = "abcdefgh"

def square_name(row, col, flipped=False):
    """
    Convert board (row, col) to chess notation like 'e4'.
    flipped=False: row 0 = rank 8 (normal/white side view)
    flipped=True:  row 0 = rank 1 (black side view)
    """
    if flipped:
        actual_col = 7 - col
        actual_row = 7 - row
    else:
        actual_col = col
        actual_row = row
    return f"{FILE_LETTERS[actual_col]}{8 - actual_row}"

def piece_letter(piece):
    """Return notation prefix for piece type. Pawns return '' (no prefix)."""
    code = piece.split("_")[1]   # "w_N" → "N"
    return "" if code == "P" else code


# ===========================================================================
# MAIN APP
# ===========================================================================
class ChessApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Chess — Basic Edition  |  By: Yosef Setiawan")
        self.root.configure(bg=COLOR_BG)
        self.root.resizable(False, False)

        # --- Core game state ---
        self.board   = make_starting_board()   # 8x8 list, current position
        self.flipped = False                   # True = board shown from black's side

        # History for undo — each entry is a full state dict saved BEFORE a move
        self.history     = []
        self.notation    = []    # list of move strings shown in move log
        self.move_number = 1     # full-move counter (increments after black moves)
        self.white_turn  = True  # True = white to move, False = black to move

        # Captured pieces — lists of piece strings e.g. ["b_Q", "b_R"]
        self.white_captured = []   # pieces white has taken from black
        self.black_captured = []   # pieces black has taken from white

        # Last move for highlight — (from_row, from_col, to_row, to_col) or None
        self.last_move = None

        # --- Drag / place state ---
        self.held_piece    = None                              # piece string being dragged, or None
        self.held_from:    Optional[Tuple[int,int]] = None    # (row, col) where piece was lifted — typed so mypy knows it's a tuple after None-check
        self.hover_sq:     Optional[Tuple[int,int]] = None    # (row, col) mouse is over — same
        self.placing_piece = None                             # piece selected from sidebar bank waiting to be placed

        # --- Clocks (count-up timers, in whole seconds) ---
        self.white_time    = 0     # total seconds white has thought
        self.black_time    = 0     # total seconds black has thought
        self.clock_running = True  # set False to pause clocks (not exposed in UI currently)

        self.setup_ui()
        self.render_board()
        self.render_sidebar()
        self.tick_clock()   # kick off the 1-second clock loop

    # =========================================================================
    # UI SETUP
    # =========================================================================
    def setup_ui(self):
        """Build canvas (board), sidebar, and bottom control bar."""

        main_frame = tk.Frame(self.root, bg=COLOR_BG)
        main_frame.pack()

        # Board canvas — all drawing happens here
        self.canvas = tk.Canvas(main_frame,
                                width=BOARD_PIXELS, height=BOARD_PIXELS,
                                bg=COLOR_BG, highlightthickness=0)
        self.canvas.pack(side=tk.LEFT)

        # Sidebar — fixed size, won't shrink to fit content
        self.sidebar = tk.Frame(main_frame, bg=COLOR_SIDEBAR,
                                width=SIDEBAR_W, height=BOARD_PIXELS)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)

        # Bottom bar — buttons left, clocks + turn indicator right
        bottom = tk.Frame(self.root, bg=COLOR_BG, height=100)
        bottom.pack(fill=tk.X)
        bottom.pack_propagate(False)

        # Action buttons
        btn_frame = tk.Frame(bottom, bg=COLOR_BG)
        btn_frame.pack(side=tk.LEFT, padx=10, pady=15)

        tk.Button(btn_frame, text="⟲ Undo",
                  font=("Arial", 11, "bold"), bg="#444", fg="white",
                  relief="flat", padx=12, pady=6,
                  command=self.undo).pack(side=tk.LEFT, padx=5)

        # Reset button — red to signal danger (full wipe)
        tk.Button(btn_frame, text="⟳ Reset",
                  font=("Arial", 11, "bold"), bg="#c0392b", fg="white",
                  relief="flat", padx=12, pady=6,
                  command=self.reset_board).pack(side=tk.LEFT, padx=5)

        # Flip button — blue to signal view change (not destructive)
        tk.Button(btn_frame, text="⇅ Flip",
                  font=("Arial", 11, "bold"), bg="#2980b9", fg="white",
                  relief="flat", padx=12, pady=6,
                  command=self.flip_board).pack(side=tk.LEFT, padx=5)

        # Right side: clocks + turn indicator
        info_frame = tk.Frame(bottom, bg=COLOR_BG)
        info_frame.pack(side=tk.RIGHT, padx=20, pady=5)

        clock_frame = tk.Frame(info_frame, bg=COLOR_BG)
        clock_frame.pack()

        # Clock labels — tick_clock() updates these every second
        self.white_clock_lbl = tk.Label(clock_frame,
                                         text="White: 0:00",
                                         font=("Courier", 12, "bold"),
                                         bg=COLOR_BG, fg=COLOR_CLOCK_ACT)
        self.white_clock_lbl.pack(side=tk.LEFT, padx=15)

        self.black_clock_lbl = tk.Label(clock_frame,
                                         text="Black: 0:00",
                                         font=("Courier", 12, "bold"),
                                         bg=COLOR_BG, fg=COLOR_CLOCK_IDLE)
        self.black_clock_lbl.pack(side=tk.LEFT, padx=15)

        # Turn indicator — large text so both players can see from across a table
        self.turn_label = tk.Label(info_frame,
                                    text="● White to move",
                                    font=("Arial", 14, "bold"),
                                    bg=COLOR_BG, fg=COLOR_W_TURN)
        self.turn_label.pack(pady=(4, 0))

        # Mouse bindings on the canvas
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Motion>",   self.on_motion)
        self.canvas.bind("<Leave>",    self.on_leave)

    # =========================================================================
    # CLOCK
    # =========================================================================
    def tick_clock(self):
        """
        Fires every 1000ms. Increments the active player's timer.
        Updates clock labels: active player = bright green, idle = dim.
        Schedules itself again via root.after — stops only if clock_running=False.
        Format: seconds → "M:SS" (e.g. 75s → "1:15")
        """
        if self.clock_running:
            if self.white_turn:
                self.white_time += 1
            else:
                self.black_time += 1

        def fmt(s):
            return f"{s // 60}:{s % 60:02d}"   # zero-pad seconds to 2 digits

        if self.white_turn:
            self.white_clock_lbl.config(text=f"White: {fmt(self.white_time)}", fg=COLOR_CLOCK_ACT)
            self.black_clock_lbl.config(text=f"Black: {fmt(self.black_time)}", fg=COLOR_CLOCK_IDLE)
        else:
            self.white_clock_lbl.config(text=f"White: {fmt(self.white_time)}", fg=COLOR_CLOCK_IDLE)
            self.black_clock_lbl.config(text=f"Black: {fmt(self.black_time)}", fg=COLOR_CLOCK_ACT)

        self.root.after(1000, self.tick_clock)   # schedule next tick in 1 second

    # =========================================================================
    # BOARD RENDERING
    # =========================================================================
    def render_board(self):
        """
        Redraw the full canvas: squares (with tints), rank/file labels, pieces.
        Square coloring priority: hover > last_move > base color.
        The held piece renders at hover_sq to show the landing preview.
        """
        self.canvas.delete("all")

        for vis_row in range(8):
            for vis_col in range(8):
                x1 = vis_col * SQUARE_SIZE
                y1 = vis_row * SQUARE_SIZE
                x2 = x1 + SQUARE_SIZE
                y2 = y1 + SQUARE_SIZE

                # Convert visual position to board position
                # When flipped: visual (0,0) = board (7,7), etc.
                if self.flipped:
                    brow, bcol = 7 - vis_row, 7 - vis_col
                else:
                    brow, bcol = vis_row, vis_col

                # Base square color — alternate by visual position (keeps board pattern correct)
                sq_color = COLOR_LIGHT if (vis_row + vis_col) % 2 == 0 else COLOR_DARK

                # Tint last-move squares — compare against board coords
                if self.last_move:
                    fr, fc, tr, tc = self.last_move
                    if (brow, bcol) == (fr, fc):
                        sq_color = COLOR_LAST_FROM
                    elif (brow, bcol) == (tr, tc):
                        sq_color = COLOR_LAST_TO

                # Hover highlight — hover_sq is already in board coords (from pixel_to_square)
                if self.held_piece and self.hover_sq == (brow, bcol):
                    sq_color = COLOR_HELD

                self.canvas.create_rectangle(x1, y1, x2, y2,
                                             fill=sq_color, outline="")

                # Draw piece at this visual square — read from board coords
                # Skip the square the piece was lifted from (it's "in hand")
                piece = self.board[brow][bcol]
                if piece and (brow, bcol) != self.held_from:
                    self.draw_piece(piece, x1, y1)

        # Rank labels (8→1 top to bottom normally; 1→8 when flipped)
        for row in range(8):
            rank_num = str(row + 1) if self.flipped else str(8 - row)
            self.canvas.create_text(5, row * SQUARE_SIZE + 10,
                                    text=rank_num, anchor="nw",
                                    fill="#888", font=("Arial", 8))

        # File labels (a→h left to right normally; h→a when flipped)
        for col in range(8):
            file_letter = FILE_LETTERS[7 - col] if self.flipped else FILE_LETTERS[col]
            self.canvas.create_text(col * SQUARE_SIZE + SQUARE_SIZE - 8,
                                    BOARD_PIXELS - 10,
                                    text=file_letter, fill="#888", font=("Arial", 8))

        # Draw held piece floating at hover square as landing preview
        # hover_sq is in board coords — convert to visual coords for pixel position
        if self.held_piece and self.hover_sq:
            hr, hc = self.hover_sq
            if self.flipped:
                vis_hr, vis_hc = 7 - hr, 7 - hc
            else:
                vis_hr, vis_hc = hr, hc
            self.draw_piece(self.held_piece, vis_hc * SQUARE_SIZE, vis_hr * SQUARE_SIZE)

    def draw_piece(self, piece, x, y):
        """
        Draw one piece at pixel position (x, y) = top-left of its square.
        Shape: oval background with unicode symbol on top.
        White pieces: white oval, dark symbol.
        Black pieces: dark oval, light symbol (for contrast on both square colors).
        Symbol size scales with SQUARE_SIZE — change the divisor to resize.
        """
        cx  = x + SQUARE_SIZE // 2   # center of square
        cy  = y + SQUARE_SIZE // 2
        pad = 8   # gap between square edge and oval — increase for smaller pieces

        color    = piece.split("_")[0]   # "w" or "b"
        fill_col = COLOR_W_PIECE if color == "w" else COLOR_B_PIECE
        out_col  = "#333333" if color == "w" else "#aaaaaa"   # outline color

        self.canvas.create_oval(x + pad, y + pad,
                                x + SQUARE_SIZE - pad, y + SQUARE_SIZE - pad,
                                fill=fill_col, outline=out_col, width=2)

        symbol    = SYMBOLS.get(piece, "?")
        text_col  = COLOR_B_PIECE if color == "w" else COLOR_W_PIECE   # contrast with fill
        font_size = SQUARE_SIZE // 2   # symbol size — smaller divisor = larger symbol

        self.canvas.create_text(cx, cy, text=symbol,
                                font=("Arial", font_size), fill=text_col)

    # =========================================================================
    # SIDEBAR
    # =========================================================================
    def render_sidebar(self):
        """
        Rebuild the sidebar from scratch:
          - Captured pieces with unicode symbols
          - Piece bank: all 6 types × 2 colors (including pawns)
          - Scrollable move log
        """
        for widget in self.sidebar.winfo_children():
            widget.destroy()

        # --- CAPTURED PIECES ---
        tk.Label(self.sidebar, text="Captured",
                 font=("Arial", 10, "bold"),
                 bg=COLOR_SIDEBAR, fg=COLOR_TEXT).pack(pady=(8, 2))

        # White's captures (what white took from black)
        w_cap_frame = tk.Frame(self.sidebar, bg=COLOR_SIDEBAR)
        w_cap_frame.pack()
        tk.Label(w_cap_frame, text="W: ",
                 font=("Arial", 9), bg=COLOR_SIDEBAR, fg="#aaa").pack(side=tk.LEFT)
        # Sort captures by piece value (Q first, pawns last)
        w_sorted = sorted(self.white_captured,
                          key=lambda p: PIECE_ORDER.index(p.split("_")[1]))
        tk.Label(w_cap_frame,
                 text=" ".join(SYMBOLS[p] for p in w_sorted) or "—",
                 font=("Arial", 13), bg=COLOR_SIDEBAR, fg="#ddd").pack(side=tk.LEFT)

        # Black's captures
        b_cap_frame = tk.Frame(self.sidebar, bg=COLOR_SIDEBAR)
        b_cap_frame.pack()
        tk.Label(b_cap_frame, text="B: ",
                 font=("Arial", 9), bg=COLOR_SIDEBAR, fg="#aaa").pack(side=tk.LEFT)
        b_sorted = sorted(self.black_captured,
                          key=lambda p: PIECE_ORDER.index(p.split("_")[1]))
        tk.Label(b_cap_frame,
                 text=" ".join(SYMBOLS[p] for p in b_sorted) or "—",
                 font=("Arial", 13), bg=COLOR_SIDEBAR, fg="#ddd").pack(side=tk.LEFT)

        # Separator line
        tk.Frame(self.sidebar, bg="#444", height=1).pack(fill=tk.X, padx=8, pady=6)

        # --- PIECE BANK ---
        tk.Label(self.sidebar, text="Add Piece",
                 font=("Arial", 10, "bold"),
                 bg=COLOR_SIDEBAR, fg=COLOR_TEXT).pack(pady=(2, 1))
        tk.Label(self.sidebar, text="click piece → click square",
                 font=("Arial", 8), bg=COLOR_SIDEBAR, fg="#777").pack()

        # Two rows: white pieces then black pieces
        # All 6 types in order: King Queen Rook Bishop Knight Pawn
        for color_label, color_code in [("White", "w"), ("Black", "b")]:
            row_frame = tk.Frame(self.sidebar, bg=COLOR_SIDEBAR)
            row_frame.pack(pady=2)
            tk.Label(row_frame, text=color_label + ":",
                     font=("Arial", 8), bg=COLOR_SIDEBAR, fg="#aaa",
                     width=5, anchor="e").pack(side=tk.LEFT)
            for ptype in ["K", "Q", "R", "B", "N", "P"]:   # P = pawn included
                piece_code = f"{color_code}_{ptype}"
                sym        = SYMBOLS[piece_code]
                fg_col     = "#ffffff" if color_code == "w" else "#cccccc"
                tk.Button(row_frame, text=sym,
                          font=("Arial", 13),
                          bg="#3a3a3a", fg=fg_col,
                          relief="flat", width=2, pady=2,
                          command=self._make_place_handler(piece_code)
                          ).pack(side=tk.LEFT, padx=1)

        # Separator line
        tk.Frame(self.sidebar, bg="#444", height=1).pack(fill=tk.X, padx=8, pady=6)

        # --- MOVE LOG ---
        tk.Label(self.sidebar, text="Move Log",
                 font=("Arial", 10, "bold"),
                 bg=COLOR_SIDEBAR, fg=COLOR_TEXT).pack()

        # Read-only scrollable text box
        self.log_box = scrolledtext.ScrolledText(
            self.sidebar,
            font=("Courier", 9),
            bg="#1a1a1a", fg="#00ff88",
            width=22, height=18,
            state="disabled",   # user cannot type here
            wrap=tk.WORD)
        self.log_box.pack(padx=6, pady=4, fill=tk.BOTH, expand=True)
        self.refresh_log()

    def refresh_log(self):
        """Rewrite the move log text box from self.notation. Auto-scrolls to latest."""
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", tk.END)
        for line in self.notation:
            self.log_box.insert(tk.END, line + "\n")
        self.log_box.see(tk.END)            # scroll to most recent move
        self.log_box.config(state="disabled")

    def update_turn_label(self):
        """Update turn indicator text and color to match whose move it is."""
        if self.white_turn:
            self.turn_label.config(text="● White to move", fg=COLOR_W_TURN)
        else:
            self.turn_label.config(text="● Black to move", fg=COLOR_B_TURN)

    # =========================================================================
    # COORDINATE HELPERS
    # =========================================================================
    def pixel_to_square(self, px, py) -> Optional[Tuple[int, int]]:
        """
        Convert pixel (px, py) to board (row, col).
        When flipped: visual top-left = board row 7, col 7.
        Returns None if click is outside the 8x8 board.
        """
        vis_col = px // SQUARE_SIZE
        vis_row = py // SQUARE_SIZE
        if not (0 <= vis_row < 8 and 0 <= vis_col < 8):
            return None
        if self.flipped:
            return (7 - vis_row, 7 - vis_col)   # invert both axes when flipped
        return (vis_row, vis_col)

    # =========================================================================
    # MOUSE INTERACTION
    # =========================================================================
    def on_motion(self, event):
        """Track hover square, redraw only when it changes (saves CPU)."""
        sq = self.pixel_to_square(event.x, event.y)
        if sq != self.hover_sq:
            self.hover_sq = sq
            self.render_board()

    def on_leave(self, event):  # pylint: disable=unused-argument
        """Mouse left canvas — clear hover highlight."""
        self.hover_sq = None
        self.render_board()

    def on_click(self, event):
        """
        Main interaction handler. Three modes:

        PLACING (sidebar piece selected):
          Next click places self.placing_piece on that square.

        PICK UP (nothing held, clicking a piece):
          Lifts the piece — removes from board, stores in self.held_piece.
          Snapshot saved HERE so undo can restore state before the move.

        PUT DOWN (holding a piece):
          On board  → moves piece there, records capture if square was occupied.
          Off board → piece is deleted (simulates knocking off the table).
        """
        sq = self.pixel_to_square(event.x, event.y)

        # --- PLACING MODE ---
        if self.placing_piece:
            if sq:
                self._save_snapshot()
                self.board[sq[0]][sq[1]] = self.placing_piece
                note = f"  +{SYMBOLS[self.placing_piece]} → {square_name(sq[0], sq[1], self.flipped)}"
                self.notation.append(note)
            self.placing_piece = None
            self.root.config(cursor="")   # restore normal cursor
            self.render_board()
            self.render_sidebar()
            return

        # --- PICK UP ---
        if self.held_piece is None:
            if sq and self.board[sq[0]][sq[1]]:
                self._save_snapshot()   # save BEFORE lifting so undo fully restores
                self.held_piece = self.board[sq[0]][sq[1]]
                self.held_from  = sq
                self.board[sq[0]][sq[1]] = None   # remove from board while in hand
                self.render_board()
            return

        # --- PUT DOWN ---
        if sq:
            # Valid square — place it, capture whatever was there
            captured = self.board[sq[0]][sq[1]]
            if captured:
                if self.white_turn:
                    self.white_captured.append(captured)
                else:
                    self.black_captured.append(captured)

            self.board[sq[0]][sq[1]] = self.held_piece
            self.last_move = (self.held_from[0], self.held_from[1], sq[0], sq[1])

            # Chess notation: piece + from_square + "-" or "x" + to_square
            cap_str  = "x" if captured else "-"
            notation = (f"{self.move_number}{'.' if self.white_turn else '..'} "
                        f"{piece_letter(self.held_piece)}"
                        f"{square_name(self.held_from[0], self.held_from[1], self.flipped)}"
                        f"{cap_str}"
                        f"{square_name(sq[0], sq[1], self.flipped)}")
            self.notation.append(notation)
        else:
            # Dropped outside board — piece is permanently removed
            self.last_move = None
            notation = (f"{self.move_number}{'.' if self.white_turn else '..'} "
                        f"{SYMBOLS[self.held_piece]} removed from board")
            self.notation.append(notation)

        # Advance turn and move counter
        if not self.white_turn:
            self.move_number += 1   # full move number increments after black moves
        self.white_turn = not self.white_turn

        self.held_piece = None
        self.held_from  = None

        self.update_turn_label()
        self.render_board()
        self.render_sidebar()

    def _make_place_handler(self, piece_code):
        """
        Factory for sidebar piece bank buttons.
        Without factory, all buttons would share the last loop value of piece_code.
        Sets placing_piece and switches cursor to crosshair to signal placing mode.
        """
        def handler():
            self.placing_piece = piece_code
            self.root.config(cursor="crosshair")
        return handler

    # =========================================================================
    # UNDO
    # =========================================================================
    def _save_snapshot(self):
        """
        Push a full game state snapshot onto self.history.
        Called before every board modification so undo can restore it.
        Board is deep-copied (nested list). Lists are shallow-copied (strings are immutable).
        notation_len records how many log entries existed so we can trim on undo.
        """
        self.history.append({
            "board":          copy.deepcopy(self.board),
            "white_turn":     self.white_turn,
            "move_number":    self.move_number,
            "white_captured": self.white_captured[:],
            "black_captured": self.black_captured[:],
            "white_time":     self.white_time,
            "black_time":     self.black_time,
            "last_move":      self.last_move,
            "notation_len":   len(self.notation),
        })

    def undo(self):
        """
        Restore board to state before the last action.
        Cancels any in-progress drag (puts piece back) or place operation first.
        Pops latest snapshot and restores all state fields from it.
        """
        # Cancel drag in progress — put piece back before undoing
        if self.held_piece:
            if self.held_from:
                self.board[self.held_from[0]][self.held_from[1]] = self.held_piece
            self.held_piece = None
            self.held_from  = None

        # Cancel placing mode
        if self.placing_piece:
            self.placing_piece = None
            self.root.config(cursor="")

        if not self.history:
            return   # nothing to undo — already at initial state

        snap = self.history.pop()

        # Restore all state from snapshot
        self.board          = snap["board"]
        self.white_turn     = snap["white_turn"]
        self.move_number    = snap["move_number"]
        self.white_captured = snap["white_captured"]
        self.black_captured = snap["black_captured"]
        self.white_time     = snap["white_time"]
        self.black_time     = snap["black_time"]
        self.last_move      = snap["last_move"]

        # Trim notation back to before the undone move
        self.notation = self.notation[:snap["notation_len"]]

        self.update_turn_label()
        self.render_board()
        self.render_sidebar()

    # =========================================================================
    # RESET & FLIP
    # =========================================================================
    def reset_board(self):
        """
        Full reset to starting position.
        Clears history, notation, captures, clocks, and any in-progress drag.
        Board orientation (flipped/normal) is preserved — use Flip to change it.
        """
        self.held_piece    = None
        self.held_from     = None
        self.placing_piece = None
        self.root.config(cursor="")

        self.board          = make_starting_board()
        self.history        = []
        self.notation       = []
        self.move_number    = 1
        self.white_turn     = True
        self.white_captured = []
        self.black_captured = []
        self.white_time     = 0   # clocks reset to zero
        self.black_time     = 0
        self.last_move      = None

        self.update_turn_label()
        self.render_board()
        self.render_sidebar()

    def flip_board(self):
        """
        Toggle board perspective between white's side (normal) and black's side.
        Toggles self.flipped flag — render_board() and pixel_to_square() both respect it.
        Does not change board data or game state, only the visual orientation.
        Rank/file labels also flip to stay correct.
        """
        self.flipped = not self.flipped
        self.render_board()   # immediate redraw with new orientation


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main_window = tk.Tk()   # renamed from "root" to avoid shadowing the class-level self.root
    app  = ChessApp(main_window)
    main_window.mainloop()   # tkinter event loop — runs until window is closed
