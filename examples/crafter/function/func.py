from PIL import Image, ImageDraw, ImageFont

def save_img(obs, task):
    img = obs["policy"]["image"][0, 0]
    img = img.transpose((1, 2, 0))
    img = Image.fromarray(img)
    img = img.resize((256, 256))
    draw = ImageDraw.Draw(img)
    draw.text((10,10), task, fill=(255,0,0))
    img.save("run_results/image.png")
    return img

def do(language, agent, env, info, trajectory):
    current_task = language
    obs = env.set_task(info[0], [current_task]) 
    action, _ = agent.act(obs, info=info[-1], deterministic=True)
    obs, r, done, info = env.step(action)
    img = save_img(obs, current_task)
    trajectory["img"].append(img)
    if all(done):
        trajectory["img"][0].save(
            "run_results/crafter.gif", 
            save_all=True,
            append_images=trajectory["img"][1:],
            duration=100,
            loop=0
        )
        trajectory["text"].append("You are dead.")
        all_text = "\n".join(trajectory["text"])
        with open("run_results/text.txt", "w") as f:
            f.write(all_text)
        exit()
    return (obs, r, done, info)

def get_obs(env_info):
    return env_info[-1][0]

def survive_and_defend(agent, env, env_info, trajectory):
    loop_counter = 0

    # Replenish drink level
    while "drink level is high" not in get_obs(env_info) and loop_counter < 30:
        do("Find water.", agent, env, env_info, trajectory)
        do("Drink water.", agent, env, env_info, trajectory)
        loop_counter += 1
        if loop_counter >= 30:
            return env_info

    # Restore energy
    while "energy is high" not in get_obs(env_info) and loop_counter < 30:
        do("Sleep.", agent, env, env_info, trajectory)
        loop_counter += 1
        if loop_counter >= 30:
            return env_info

    # Defend against threats
    if "zombie" in get_obs(env_info):
        while "zombie" in get_obs(env_info) and loop_counter < 30:
            do("Kill the zombie.", agent, env, env_info, trajectory)
            loop_counter += 1
            if loop_counter >= 30:
                return env_info

    if "skeleton" in get_obs(env_info):
        while "skeleton" in get_obs(env_info) and loop_counter < 30:
            do("Kill the skeleton.", agent, env, env_info, trajectory)
            loop_counter += 1
            if loop_counter >= 30:
                return env_info

    # At this point, further actions could vary depending on the situation
    # For example, we might want to craft better tools or mine resources
    # But these would be beyond the scope of this immediate survival plan

    return env_info
