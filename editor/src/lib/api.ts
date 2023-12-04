export async function get_user_dpasp_runner_url(userid){
    try {        
        const cm_response = await fetch(
            `http://container-manager/container_for_user/${userid}`
        )

        if (!cm_response.ok) {
        throw new Error(`Unable to get requested container id from container-manager`);
        }

        const container_id = (await cm_response.json()).id

        console.log(container_id)
        return `http://dpasp-instance-${container_id}`
    } catch (e) {
        console.error(`Could not get user's dpasp runner instance`)
        throw e
    }
}