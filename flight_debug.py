#!/usr/bin/env python3
"""
Flight tracker hardware diagnostics - run this to debug display/button issues.

Usage:
  python3 flight_debug.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_whisplay_driver():
    """Test WhisPlayBoard driver and show available APIs."""
    print("\n" + "=" * 60)
    print("WHISPLAY HARDWARE TEST")
    print("=" * 60)
    
    try:
        sys.path.insert(0, "/home/aaron/Whisplay/Driver")
        from WhisPlay import WhisPlayBoard
        
        print("✓ WhisPlay driver imported successfully")
        
        # Initialize board
        board = WhisPlayBoard()
        print("✓ WhisPlayBoard initialized")
        
        # List available methods
        methods = [m for m in dir(board) if not m.startswith('_')]
        print(f"\n📡 Available WhisPlayBoard methods:")
        for method in sorted(methods):
            print(f"   - {method}")
        
        # Test specific methods
        print(f"\n🔍 Testing specific APIs:")
        
        # Backlight
        if hasattr(board, "set_backlight"):
            print("   ✓ set_backlight() - display brightness control")
            try:
                board.set_backlight(100)
                print("     Set to 100% brightness")
            except Exception as e:
                print(f"     Error: {e}")
        
        # Display methods
        display_methods = ["draw_image", "display", "show_image", "draw", "fill_screen"]
        found_display = False
        for method in display_methods:
            if hasattr(board, method):
                print(f"   ✓ {method}() - DISPLAY METHOD FOUND")
                found_display = True
        
        if not found_display:
            print("   ✗ No display methods found!")
        
        # Button methods
        button_methods = ["get_button", "get_button_state", "button_pressed", "read_button"]
        found_button = False
        for method in button_methods:
            if hasattr(board, method):
                print(f"   ✓ {method}() - BUTTON METHOD FOUND")
                found_button = True
                
                # Try to call it
                try:
                    if method == "get_button":
                        val = board.get_button()
                    elif method == "get_button_state":
                        val = board.get_button_state()
                    elif method == "button_pressed":
                        val = board.button_pressed()
                    elif method == "read_button":
                        val = board.read_button()
                    print(f"     Current state: {val}")
                except Exception as e:
                    print(f"     Error reading: {e}")
        
        if not found_button:
            print("   ✗ No button methods found!")
        
        # Try test display pattern
        print(f"\n🎨 Testing display with blue pattern...")
        try:
            from PIL import Image
            
            # Create test image
            test_img = Image.new("RGB", (240, 280), color=(10, 50, 100))
            pixels = list(test_img.getdata())
            rgb565_data = []
            for r, g, b in pixels:
                rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                rgb565_data.extend([(rgb565 >> 8) & 0xFF, rgb565 & 0xFF])
            
            if hasattr(board, "draw_image"):
                board.draw_image(0, 0, 240, 280, rgb565_data)
                print("   ✓ Test pattern sent via draw_image()")
                print("   💻 You should see a blue screen on your display!")
            elif hasattr(board, "display"):
                board.display(rgb565_data)
                print("   ✓ Test pattern sent via display()")
                print("   💻 You should see a blue screen on your display!")
        except Exception as e:
            print(f"   ✗ Failed to send test pattern: {e}")
        
        # Button test
        print(f"\n🔘 Button test - press the button in next 10 seconds...")
        if found_button:
            button_method = None
            for method in ["get_button", "get_button_state", "button_pressed", "read_button"]:
                if hasattr(board, method):
                    button_method = method
                    break
            
            if button_method:
                last_state = False
                for i in range(20):  # 10 seconds at 0.5s intervals
                    try:
                        if button_method == "get_button":
                            state = board.get_button()
                        elif button_method == "get_button_state":
                            state = board.get_button_state()
                        elif button_method == "button_pressed":
                            state = board.button_pressed()
                        elif button_method == "read_button":
                            state = board.read_button()
                        
                        if state and not last_state:
                            print(f"   ✓ 🔘 BUTTON PRESSED DETECTED!")
                            last_state = state
                        elif state != last_state:
                            print(f"   Button state changed: {last_state} -> {state}")
                            last_state = state
                    except Exception as e:
                        print(f"   Error polling button: {e}")
                    
                    time.sleep(0.5)
                    if i % 4 == 3:
                        print(f"      Waiting... ({(i+1)//2}s)")
                
                print("   ✓ Button test complete")
        else:
            print("   ⚠ No button method found to test")
        
        return True
        
    except ImportError as e:
        print(f"✗ WhisPlay driver not available: {e}")
        print("   Make sure to run this on your Raspberry Pi")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_config():
    """Test flight tracker configuration."""
    print("\n" + "=" * 60)
    print("FLIGHT TRACKER CONFIG TEST")
    print("=" * 60)
    
    try:
        from flight.config import load_config
        
        config = load_config()
        print(f"✓ Config loaded: {len(config.locations)} locations")
        for i, loc in enumerate(config.locations, 1):
            print(f"   {i}. {loc.name}")
        
        return True
    except Exception as e:
        print(f"✗ Config error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all diagnostics."""
    print("\n" + "🛠️  " * 15)
    print("FLIGHT TRACKER DIAGNOSTICS")
    print("🛠️  " * 15)
    
    config_ok = test_config()
    hardware_ok = test_whisplay_driver()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    if config_ok:
        print("✓ Configuration OK")
    else:
        print("✗ Configuration ERROR")
    
    if hardware_ok:
        print("✓ Hardware OK")
    else:
        print("✗ Hardware ERROR")
    
    if config_ok and hardware_ok:
        print("\n✅ System ready! You can run: python3 flight_tracker.py")
        print("\n⏱️  Monitor output with: --debug flag for verbose logging")
        print("   python3 flight_tracker.py --debug")
    else:
        print("\n⚠️  Fix the errors above before running flight_tracker.py")
    
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
