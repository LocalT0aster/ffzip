tg720() {
    local in="$1"
    local out="${2:-${in%.*}_tg720.mp4}"

    # Probe resolution
    local width height
    read width height < <(ffprobe -v error -select_streams v:0 \
        -show_entries stream=width,height -of csv=p=0 "$in")

    # Decide scaling
    local scale_filter
    if (( width < 1 || height < 1 )); then
        echo "Could not read resolution." >&2
        return 1
    fi

    # smaller side
    local min_side=$(( width < height ? width : height ))

    if (( min_side > 720 )); then
        # Scale so smaller side becomes 720; keep aspect ratio
        # We detect orientation:
        if (( width < height )); then
            # Vertical → width becomes 720
            scale_filter="scale=720:-2:flags=lanczos,setsar=1"
        else
            # Horizontal → height becomes 720
            scale_filter="scale=-2:720:flags=lanczos,setsar=1"
        fi
    else
        # No scaling needed
        scale_filter="scale=${width}:${height},setsar=1"
    fi

    ffmpeg -i "$in" \
      -vf "$scale_filter" \
      -c:v libx264 -profile:v baseline -level 3.1 \
      -b:v 2000k -maxrate 2100k -bufsize 4000k \
      -c:a aac -b:a 128k -ar 48000 \
      -movflags +faststart \
      "$out"
}
