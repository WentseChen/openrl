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
    action, _ = agent.act(info[0], deterministic=True)
    obs, r, done, info = env.step(action, given_task=[current_task])
    img = save_img(obs, current_task)
    trajectory.append(img)
    if all(done):
        trajectory[0].save(
            "run_results/crafter.gif", 
            save_all=True, 
            append_images=trajectory[1:], 
            duration=100, 
            loop=0
        )
        exit()
    return (obs, r, done, info)

def get_obs(info):
    return info[-1][0]
def survival_prep(agent, env, env_info, trajectory):
    loop_counter = 0
    inventory_obs = get_obs(env_info)
    
    # Chop trees until wood is obtained or the loop counter reaches 30.
    while "wood" not in inventory_obs and loop_counter < 30:
        env_info = do("Chop trees.", agent, env, env_info, trajectory)
        inventory_obs = get_obs(env_info)
        loop_counter += 1
        if loop_counter >= 30:
            return env_info
    
    # Craft a wood pickaxe if there is wood in the inventory.
    if "wood" in inventory_obs:
        env_info = do("Craft wood_pickaxe.", agent, env, env_info, trajectory)
        loop_counter += 1

    # Craft a wood sword if there is wood in the inventory.
    if "wood" in inventory_obs and loop_counter < 30:
        env_info = do("Craft wood_sword.", agent, env, env_info, trajectory)
        loop_counter += 1

    return env_info
