#!/usr/bin/env python3
"""Fix the agent_manager.py _generate_response method"""

# Read the file
with open('c:\\Users\\djohn\\.aria\\src\\agent_manager.py', 'r', encoding='utf-8') as f:
    content = f.read()

# The old responses dictionary and default response
old_code = '''        responses = {
            'melody': "I can help you create a beautiful melody! Let's start by choosing a key and scale. Would you prefer major (happy/bright) or minor (sad/dark)?",
            'chord': "Great choice! For chord progressions, I recommend starting with the classic I-V-vi-IV progression. In C major, that would be C-G-Am-F. Would you like to try this or explore something more unique?",
            'drum': "Let's build a drum pattern! For a standard house beat, try kick on beats 1, 2, 3, 4, hi-hats on every 8th note, and snare on beats 2 and 4. What genre are you working in?",
            'bass': "A solid bass line is crucial! For a supportive bass, try playing the root notes of your chord progression. For something more melodic, we can add passing tones and rhythmic variations.",
            'intro': "For an intro, consider starting sparse - maybe just a pad or atmospheric sound. Gradually introduce elements to build anticipation. How long do you want the intro to be?",
            'drop': "Building to a drop is all about tension and release! Try filtering out highs before the drop, then bring everything back in with full energy. What elements do you want in your drop?",
        }
        
        # Check for keywords
        for keyword, response in responses.items():
            if keyword in user_message:
                return response
                
        # Default response
        return "That's an interesting idea! I can help you develop that further. Could you tell me more about the style or mood you're going for?"'''

# The new expanded responses dictionary with genres and varied defaults
new_code = '''        responses = {
            # Original musical elements
            'melody': "I can help you create a beautiful melody! Try starting with a simple motif in C major - maybe C-E-G-E. Then expand it by adding passing tones and rhythmic variations. Would you like me to suggest a specific melodic contour?",
            'chord': "Great choice! For chord progressions, try the classic I-V-vi-IV (C-G-Am-F in C major) for a timeless sound, or ii-V-I for jazz vibes. For something modern, try vi-IV-I-V. Which direction appeals to you?",
            'drum': "Let's build a drum pattern! For house: kick on all 4 beats, snare on 2 & 4, hi-hats on 8ths. For hip hop: kick on 1 & 3, snare on 2 & 4 with swung hi-hats. For trap: fast hi-hats with rolls and a hard 808 kick. What vibe are you after?",
            'bass': "A solid bass line anchors everything! Try root-fifth-octave patterns for stability, or walking bass for movement. For EDM, try sidechaining the bass to the kick. For funk, use syncopation and ghost notes. Want specific note recommendations?",
            'intro': "For an intro, start sparse and build tension. Try a filtered pad or atmospheric sounds, then gradually add elements. 4-8 bars works well. Use risers or reverse cymbals leading into the verse. What energy level should the intro have?",
            'drop': "The drop is all about impact! Remove low frequencies before the drop (filter sweep), then bring everything back with full force. Layer your kick with a sub-bass for power. Add white noise sweeps for energy. What genre is this drop for?",
            
            # Genres
            'pop': "Pop music is all about catchy hooks and clean production! Start with a strong verse-chorus structure, use sidechain compression for that pumping feel, and keep the arrangement simple but effective. Try four-on-the-floor kicks with layered claps. Want help with the hook?",
            'hip hop': "Hip hop is built on groove and attitude! Start with a solid drum break or programmed beat, add a bass line that hits hard, and layer melodic elements sparingly. Use swung rhythms for that classic feel. Boom bap or trap style?",
            'house': "House music is all about the four-on-the-floor! Keep the kick steady, add open hi-hats on the off-beats, and use a pumping bass sidechained to the kick. Build energy with filters and risers. Try 124-128 BPM for classic house vibes.",
            'trap': "Trap needs those hard-hitting 808s and fast hi-hats! Use triplet or 32nd-note hi-hat rolls, a booming sub-bass, and dark, cinematic synths. Keep the tempo around 140 BPM. Add vocal chops or brass stabs for that modern trap sound.",
            'rock': "Rock is about raw energy and live feel! Start with a powerful drum groove, add a driving bass line, then layer guitars - rhythm and lead. Use distortion and compression for grit. Don't forget the space for the vocals to cut through.",
            'lo-fi': "Lo-fi is all about that chill, nostalgic vibe! Use vinyl crackle samples, jazzy chord progressions with 7ths and 9ths, dusty drums with swing, and soft Rhodes or piano sounds. Keep it mellow around 70-90 BPM with plenty of reverb.",
            'techno': "Techno is hypnotic and driving! Use repetitive, evolving synth patterns, a pounding kick drum, and minimal but effective percussion. Build tension with filter sweeps and gradual changes. Try 125-135 BPM with industrial textures.",
            'rnb': "R&B is smooth and soulful! Use jazzy chord progressions, swung grooves, warm bass lines, and space for vocals. Layer pads and keys for atmosphere. Keep the drums tight but groovy. Try 60-100 BPM for that laid-back feel.",
            'edm': "EDM is about big energy and festival-ready sounds! Start with a massive kick, layered supersaw synths, and a pumping sidechain. Build huge drops with risers, impacts, and white noise. Try 128 BPM for big room or 150 for hardstyle.",
            
            # Beat types and patterns
            'beat': "Let's create that beat! Start with the foundation - kick and snare placement defines the groove. Then add hi-hats for energy and rhythmic interest. Layer percussion for texture. What genre should this beat fit?",
            'groove': "Groove is about feel and pocket! Focus on the interaction between kick, snare, and bass. Use ghost notes, swung rhythms, and space between hits. The best grooves make people move without thinking about it. What instrument should carry the groove?",
            'rhythm': "Rhythm is the heartbeat of music! Consider syncopation, polyrhythms, or straight-ahead patterns. Layer different rhythmic elements - some on the beat, some off. Use velocity variation for human feel. What's the tempo and time signature?",
            'pattern': "Patterns create repetition and interest! Try varying patterns every 4 or 8 bars, add fills at transitions, and use call-and-response between instruments. Build complexity gradually. Should this pattern be simple or complex?",
            
            # Additional musical elements
            'hook': "A great hook is memorable and singable! Keep it simple, use repetition, and make it the peak energy moment. Try a catchy melodic phrase or a rhythmic vocal chop. The hook should stick in your head after one listen. Want me to suggest a melodic contour?",
            'verse': "Verses tell the story and build to the chorus! Keep the energy lower than the chorus, use sparser instrumentation, and create contrast. Build gradually through the verse to lead into the hook. How many verses are you planning?",
            'chorus': "The chorus is the peak! Layer more instruments, raise the vocal register, add harmonies, and increase the rhythmic density. This is where everything comes together. Make it the most memorable section of the song.",
            'bridge': "Bridges provide contrast and refresh the ear! Change the chord progression, shift the energy level, or introduce a new element. It's a departure before returning to the final chorus. What mood should the bridge have?",
            'outro': "The outro wraps things up! You can fade out gradually, end abruptly for impact, or strip back to just one element. Consider a callback to the intro for bookend effect. How do you want the listener to feel at the end?",
            'arp': "Arpeggios add movement and energy! Try different patterns - up, down, up-down, or random. Use them to fill space between chords or as a main melodic element. Add velocity variation for a more human feel. What synth sound should the arp use?",
            'pad': "Pads create atmosphere and glue the mix together! Use long attack and release times, layer multiple octaves, and add subtle movement with LFOs. Pads sit in the background but fill out the frequency spectrum. Want a bright or dark pad sound?",
            'lead': "Lead sounds cut through the mix! Choose a sound with presence in the 2-5kHz range, add some saturation or distortion for edge, and use portamento for expressive slides. Leads should be catchy and memorable. What style of lead are you thinking?",
            'pluck': "Pluck sounds are great for rhythmic elements! Use short attack and medium decay, add reverb for space, and layer with a sub-bass for body. Plucks work well for arpeggios and staccato melodies. What genre is this for?",
            'fx': "FX add excitement and transitions! Use risers before drops, impacts on downbeats, downlifters for energy reduction, and sweeps for movement. Don't overdo it - FX should enhance, not distract. Where in the arrangement do you need FX?",
            'synth': "Synthesis offers endless sound design possibilities! Start with basic waveforms - saw for bright sounds, square for hollow sounds, sine for pure bass, triangle for soft tones. Then add filters, envelopes, and effects. What kind of synth sound do you want?",
            'sample': "Sampling is a creative way to add texture! Try chopping breaks for drums, pitching vocals for melodic content, or layering found sounds for unique atmosphere. Make sure to clear samples if releasing commercially. What type of sample are you working with?",
            'loop': "Loops are great building blocks! Use them as starting points, chop and rearrange for originality, or layer multiple loops for complexity. Adjust timing and pitch to fit your project. What kind of loop - drums, melodic, or texture?",
        }
        
        # Check for keywords
        for keyword, response in responses.items():
            if keyword in user_message:
                return response
                
        # Default responses - helpful and varied, not questions
        default_responses = [
            "I can help you build that! Let's start by establishing the tempo and key, then layer in the foundational elements like drums and bass.",
            "Great idea! Try sketching out the main sections first - intro, verse, chorus, and outro. Then we can fill in the details.",
            "Let's make this happen! Start with a simple foundation and build up layer by layer. The first idea doesn't have to be perfect - we'll refine as we go.",
            "I'm ready to help! Begin with the element that inspires you most - maybe a melody, a drum pattern, or a chord progression - and we'll build around that.",
            "Sounds exciting! Try creating a rough arrangement first with placeholder sounds, then replace and refine each element until it all comes together.",
            "Let's create something great! Focus on the core groove or melody first, get that feeling right, then add supporting elements to enhance it.",
            "I'm on it! Music production is about layering - start simple, make sure each element serves the song, and don't be afraid to remove things that don't work.",
            "Absolutely! Remember that contrast is key - vary the energy between sections, use dynamics, and give the listener moments of surprise and familiarity.",
        ]
        
        # Return a random default response to avoid repetition
        import random
        return random.choice(default_responses)'''

# Replace
if old_code in content:
    content = content.replace(old_code, new_code)
    with open('c:\\Users\\djohn\\.aria\\src\\agent_manager.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("SUCCESS: Updated agent_manager.py")
else:
    print("FAIL: Could not find the old code pattern")
