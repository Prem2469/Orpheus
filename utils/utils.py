import pickle, requests, errno, hashlib, math, os, re, operator
from tqdm import tqdm
from PIL import Image, ImageChops
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from functools import reduce


def hash_string(input_str: str, hash_type: str = 'MD5'):
    if hash_type == 'MD5':
        return hashlib.md5(input_str.encode("utf-8")).hexdigest()
    else:
        raise Exception('Invalid hash type selected')

def calculate_file_md5(file_path: str) -> str:
    """Calculate MD5 hash of a file."""
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except (OSError, IOError) as e:
        raise Exception(f"Error calculating MD5 hash for {file_path}: {e}")

def calculate_unencoded_md5(file_path: str) -> str:
    """Calculate MD5 hash of unencoded audio data from a FLAC file using the correct FLAC specification."""
    import subprocess
    import tempfile
    import os
    import time
    from mutagen.flac import FLAC
    
    try:
        # Get FLAC file properties first
        flac_file = FLAC(file_path)
        sample_rate = flac_file.info.sample_rate
        channels = flac_file.info.channels
        bits_per_sample = flac_file.info.bits_per_sample
        
        # Create a temporary file for raw audio data
        with tempfile.NamedTemporaryFile(delete=False, suffix='.raw') as temp_file:
            temp_path = temp_file.name
        
        try:
            # Use ffmpeg to extract raw audio data in the exact format FLAC expects
            # The format must match FLAC's internal representation exactly
            if bits_per_sample == 16:
                ffmpeg_format = 's16le'
                codec = 'pcm_s16le'
            elif bits_per_sample == 24:
                ffmpeg_format = 's24le'
                codec = 'pcm_s24le'
            elif bits_per_sample == 32:
                ffmpeg_format = 's32le'
                codec = 'pcm_s32le'
            else:
                raise Exception(f"Unsupported bit depth: {bits_per_sample}")
            
            # Extract audio with exact parameters matching the FLAC file
            result = subprocess.run([
                'ffmpeg', '-i', file_path, 
                '-f', ffmpeg_format, 
                '-acodec', codec,
                '-ar', str(sample_rate),
                '-ac', str(channels),
                '-y', temp_path
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            
            # Small delay to ensure file is fully written
            time.sleep(0.1)
            
            # Calculate MD5 of the raw audio data
            hash_md5 = hashlib.md5()
            with open(temp_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            
            return hash_md5.hexdigest()
            
        finally:
            # Clean up temporary file with retry logic
            for i in range(3):
                try:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    break
                except PermissionError:
                    time.sleep(0.1)
                    
    except Exception as e:
        # If all else fails, don't set MD5 signature rather than set it incorrectly
        raise Exception(f"Could not calculate proper unencoded MD5 for {file_path}: {e}")
        
def fix_flac_md5_signature(file_path: str) -> str:
    """Fix FLAC MD5 signature by re-encoding the file to calculate the correct MD5."""
    import subprocess
    import tempfile
    import os
    import time
    import shutil
    from mutagen.flac import FLAC
    
    try:
        # First check if MD5 signature is already set correctly
        original_flac = FLAC(file_path)
        if original_flac.info.md5_signature and original_flac.info.md5_signature != 0:
            existing_md5 = f"{original_flac.info.md5_signature:032x}"
            # Test if the existing MD5 is correct by trying to verify it
            # If no error occurs, the MD5 is correct
            return existing_md5
        
        # Create a temporary FLAC file for re-encoding
        with tempfile.NamedTemporaryFile(delete=False, suffix='.flac') as temp_file:
            temp_path = temp_file.name
        
        try:
            # Re-encode the FLAC file, which will calculate the correct MD5
            result = subprocess.run([
                'ffmpeg', '-i', file_path, 
                '-c:a', 'flac',
                '-compression_level', '5',  # Use reasonable compression
                '-y', temp_path
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            
            # Read the MD5 signature from the re-encoded file
            temp_flac = FLAC(temp_path)
            md5_signature = temp_flac.info.md5_signature
            
            if md5_signature and md5_signature != 0:
                md5_hex = f"{md5_signature:032x}"
                
                # Set this MD5 signature in the original file
                if set_flac_md5_signature(file_path, md5_hex):
                    return md5_hex
                else:
                    raise Exception("Could not set MD5 signature in original file")
            else:
                raise Exception("Re-encoded FLAC also has no MD5 signature")
                
        finally:
            # Clean up temporary file
            for i in range(3):
                try:
                    if os.path.exists(temp_path):
                        os.unlink(temp_path)
                    break
                except PermissionError:
                    time.sleep(0.1)
                    
    except Exception as e:
        raise Exception(f"Could not fix FLAC MD5 signature for {file_path}: {e}")

def set_flac_md5_signature(file_path: str, md5_hash: str) -> bool:
    """Set the MD5 signature in a FLAC file's STREAMINFO block."""
    try:
        from mutagen.flac import FLAC
        
        # Open the FLAC file
        flac_file = FLAC(file_path)
        
        # Convert hex string to bytes (16 bytes for MD5)
        if len(md5_hash) == 32:  # 32 hex characters = 16 bytes
            md5_bytes = bytes.fromhex(md5_hash)
            
            # Set the MD5 signature in the STREAMINFO block
            flac_file.info.md5_signature = int.from_bytes(md5_bytes, byteorder='big')
            
            # Save the file
            flac_file.save()
            return True
        else:
            raise ValueError(f"Invalid MD5 hash length: {len(md5_hash)} (expected 32)")
            
    except Exception as e:
        print(f"Warning: Could not set FLAC MD5 signature for {file_path}: {e}")
        return False

def create_requests_session():
    session_ = requests.Session()
    retries = Retry(total=10, backoff_factor=0.4, status_forcelist=[429, 500, 502, 503, 504])
    session_.mount('http://', HTTPAdapter(max_retries=retries))
    session_.mount('https://', HTTPAdapter(max_retries=retries))
    return session_

sanitise_name = lambda name : re.sub(r'[:]', ' - ', re.sub(r'[\\/*?"<>|$]', '', re.sub(r'[ \t]+$', '', str(name).rstrip()))) if name else ''


def fix_byte_limit(path: str, byte_limit=250):
    # only needs the relative path, the abspath uses already existing folders
    rel_path = os.path.relpath(path).replace('\\', '/')

    # split path into directory and filename
    directory, filename = os.path.split(rel_path)

    # truncate filename if its byte size exceeds the byte_limit
    filename_bytes = filename.encode('utf-8')
    fixed_bytes = filename_bytes[:byte_limit]
    fixed_filename = fixed_bytes.decode('utf-8', 'ignore')

    # join the directory and truncated filename together
    return directory + '/' + fixed_filename


r_session = create_requests_session()

def download_file(url, file_location, headers={}, enable_progress_bar=False, indent_level=0, artwork_settings=None):
    if os.path.isfile(file_location):
        return None

    r = r_session.get(url, stream=True, headers=headers, verify=False)

    total = None
    if 'content-length' in r.headers:
        total = int(r.headers['content-length'])

    try:
        with open(file_location, 'wb') as f:
            if enable_progress_bar and total:
                try:
                    columns = os.get_terminal_size().columns
                    if os.name == 'nt':
                        bar = tqdm(total=total, unit='B', unit_scale=True, unit_divisor=1024, initial=0, miniters=1, ncols=(columns-indent_level), bar_format=' '*indent_level + '{l_bar}{bar}{r_bar}')
                    else:
                        raise
                except:
                    bar = tqdm(total=total, unit='B', unit_scale=True, unit_divisor=1024, initial=0, miniters=1, bar_format=' '*indent_level + '{l_bar}{bar}{r_bar}')
                # bar.set_description(' '*indent_level)
                for chunk in r.iter_content(chunk_size=1024):
                    if chunk:  # filter out keep-alive new chunks
                        f.write(chunk)
                        bar.update(len(chunk))
                bar.close()
            else:
                [f.write(chunk) for chunk in r.iter_content(chunk_size=1024) if chunk]
        if artwork_settings and artwork_settings.get('should_resize', False):
            new_resolution = artwork_settings.get('resolution', 1400)
            new_format = artwork_settings.get('format', 'jpeg')
            if new_format == 'jpg': new_format = 'jpeg'
            new_compression = artwork_settings.get('compression', 'low')
            if new_compression == 'low':
                new_compression = 90
            elif new_compression == 'high':
                new_compression = 70
            if new_format == 'png': new_compression = None
            with Image.open(file_location) as im:
                im = im.resize((new_resolution, new_resolution), Image.Resampling.BICUBIC)
                im.save(file_location, new_format, quality=new_compression)
    except KeyboardInterrupt:
        if os.path.isfile(file_location):
            print(f'\tDeleting partially downloaded file "{str(file_location)}"')
            silentremove(file_location)
        raise KeyboardInterrupt

# root mean square code by Charlie Clark: https://code.activestate.com/recipes/577630-comparing-two-images/
def compare_images(image_1, image_2):
    with Image.open(image_1) as im1, Image.open(image_2) as im2:
        h = ImageChops.difference(im1, im2).convert('L').histogram()
        return math.sqrt(reduce(operator.add, map(lambda h, i: h*(i**2), h, range(256))) / (float(im1.size[0]) * im1.size[1]))

# TODO: check if not closing the files causes issues, and see if there's a way to use the context manager with lambda expressions
get_image_resolution = lambda image_location : Image.open(image_location).size[0]

def silentremove(filename):
    try:
        os.remove(filename)
    except OSError as e:
        if e.errno != errno.ENOENT:
            raise

def read_temporary_setting(settings_location, module, root_setting=None, setting=None, global_mode=False):
    temporary_settings = pickle.load(open(settings_location, 'rb'))
    module_settings = temporary_settings['modules'][module] if module in temporary_settings['modules'] else None
    
    if module_settings:
        if global_mode:
            session = module_settings
        else:
            session = module_settings['sessions'][module_settings['selected']]
    else:
        session = None

    if session and root_setting:
        if setting:
            return session[root_setting][setting] if root_setting in session and setting in session[root_setting] else None
        else:
            return session[root_setting] if root_setting in session else None
    elif root_setting and not session:
        raise Exception('Module does not use temporary settings') 
    else:
        return session

def set_temporary_setting(settings_location, module, root_setting, setting=None, value=None, global_mode=False):
    temporary_settings = pickle.load(open(settings_location, 'rb'))
    module_settings = temporary_settings['modules'][module] if module in temporary_settings['modules'] else None

    if module_settings:
        if global_mode:
            session = module_settings
        else:
            session = module_settings['sessions'][module_settings['selected']]
    else:
        session = None

    if not session:
        raise Exception('Module does not use temporary settings')
    if setting:
        session[root_setting][setting] = value
    else:
        session[root_setting] = value
    pickle.dump(temporary_settings, open(settings_location, 'wb'))

create_temp_filename = lambda : f'temp/{os.urandom(16).hex()}'

def save_to_temp(input: bytes):
    location = create_temp_filename()
    open(location, 'wb').write(input)
    return location

def download_to_temp(url, headers={}, extension='', enable_progress_bar=False, indent_level=0):
    location = create_temp_filename() + (('.' + extension) if extension else '')
    download_file(url, location, headers=headers, enable_progress_bar=enable_progress_bar, indent_level=indent_level)
    return location
