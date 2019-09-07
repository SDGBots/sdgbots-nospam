# SCP-079-NOSPAM - Block spam in groups
# Copyright (C) 2019 SCP-079 <https://scp-079.org>
#
# This file is part of SCP-079-NOSPAM.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
from copy import deepcopy
from time import sleep

from pyrogram import Client

from .. import glovar
from .channel import ask_for_help, get_debug_text, share_data, share_regex_count
from .etc import code, general_link, get_full_name, get_now, message_link, thread
from .file import save
from .filters import is_nm_text
from .group import leave_group
from .telegram import get_admins, get_group_info, send_message
from .user import add_bad_user, ban_user, get_user

# Enable logging
logger = logging.getLogger(__name__)


def backup_files(client: Client) -> bool:
    # Backup data files to BACKUP
    try:
        for file in glovar.file_list:
            try:
                share_data(
                    client=client,
                    receivers=["BACKUP"],
                    action="backup",
                    action_type="pickle",
                    data=file,
                    file=f"data/{file}"
                )
                sleep(5)
            except Exception as e:
                logger.warning(f"Send backup file {file} error: {e}", exc_info=True)

        return True
    except Exception as e:
        logger.warning(f"Backup error: {e}", exc_info=True)

    return False


def interval_min_15(client: Client) -> bool:
    # Execute every 15 minutes
    try:
        # Check user's name
        now = get_now()
        user_ids = deepcopy(glovar.user_ids)
        for uid in user_ids:
            if any([now - user_ids[uid]["join"][gid] < glovar.time_new for gid in user_ids[uid]["join"]]):
                user = get_user(client, uid)
                if user:
                    name = get_full_name(user)
                    if is_nm_text(name):
                        text = (f"项目编号：{code(glovar.sender)}\n"
                                f"用户 ID：{code(uid)}\n"
                                f"操作等级：{code('自动封禁')}\n"
                                f"规则：{code('名称复查')}\n"
                                f"用户昵称：{code(name)}\n")
                        result = send_message(client, glovar.logging_channel_id, text)
                        if result:
                            g_list = list(user_ids[uid]["join"])
                            gid = sorted(g_list, key=lambda g: user_ids[uid]["join"][g], reverse=True)[0]
                            add_bad_user(client, uid)
                            ban_user(client, gid, uid)
                            ask_for_help(client, "ban", gid, uid)
                            text = get_debug_text(client, gid)
                            text += (f"用户 ID：{code(uid)}\n"
                                     f"执行操作：{code('名称封禁')}\n"
                                     f"证据留存：{general_link(result.message_id, message_link(result))}\n")
                            thread(send_message, (client, glovar.debug_channel_id, text))

        return True
    except Exception as e:
        logger.warning(f"Interval min 10 error: {e}", exc_info=True)

    return False


def reset_data() -> bool:
    # Reset user data every month
    try:
        glovar.bad_ids = {
            "channels": set(),
            "temp": set(),
            "users": set()
        }
        save("bad_ids")

        glovar.except_ids = {
            "temp": set()
        }
        save("except_ids")

        glovar.user_ids = {}
        save("user_ids")

        glovar.watch_ids = {
            "ban": {},
            "delete": {}
        }
        save("watch_ids")

        return True
    except Exception as e:
        logger.warning(f"Reset data error: {e}", exc_info=True)

    return False


def send_count(client: Client) -> bool:
    # Send regex count to REGEX
    if glovar.locks["regex"].acquire():
        try:
            for word_type in glovar.regex:
                share_regex_count(client, word_type)
                word_list = list(eval(f"glovar.{word_type}_words"))
                for word in word_list:
                    eval(f"glovar.{word_type}_words")[word] = 0

                save(f"{word_type}_words")

            return True
        except Exception as e:
            logger.warning(f"Send count error: {e}", exc_info=True)
        finally:
            glovar.locks["regex"].release()

    return False


def update_admins(client: Client) -> bool:
    # Update admin list every day
    if glovar.locks["admin"].acquire():
        group_list = list(glovar.admin_ids)
        for gid in group_list:
            try:
                should_leave = True
                reason = "permissions"
                admin_members = get_admins(client, gid)
                if admin_members and any([admin.user.is_self for admin in admin_members]):
                    glovar.admin_ids[gid] = {admin.user.id for admin in admin_members
                                             if not admin.user.is_bot or admin.user.id in glovar.bot_ids}
                    if glovar.user_id not in glovar.admin_ids[gid]:
                        reason = "user"
                    else:
                        for admin in admin_members:
                            if admin.user.is_self:
                                if admin.can_delete_messages and admin.can_restrict_members:
                                    should_leave = False

                    if should_leave:
                        group_name, group_link = get_group_info(client, gid)
                        share_data(
                            client=client,
                            receivers=["MANAGE"],
                            action="leave",
                            action_type="request",
                            data={
                                "group_id": gid,
                                "group_name": group_name,
                                "group_link": group_link,
                                "reason": reason
                            }
                        )
                        if reason == "permissions":
                            reason = "权限缺失"
                        elif reason == "user":
                            reason = "缺失 USER"

                        debug_text = (f"项目编号：{general_link(glovar.project_name, glovar.project_link)}\n"
                                      f"群组名称：{general_link(group_name, group_link)}\n"
                                      f"群组 ID：{code(gid)}\n"
                                      f"状态：{code(reason)}\n")
                        thread(send_message, (client, glovar.debug_channel_id, debug_text))
                elif admin_members is False or any([admin.user.is_self for admin in admin_members]) is False:
                    # Bot is not in the chat, leave automatically without approve
                    group_name, group_link = get_group_info(client, gid)
                    leave_group(client, gid)
                    share_data(
                        client=client,
                        receivers=["MANAGE"],
                        action="leave",
                        action_type="info",
                        data=gid
                    )
                    debug_text = (f"项目编号：{general_link(glovar.project_name, glovar.project_link)}\n"
                                  f"群组名称：{general_link(group_name, group_link)}\n"
                                  f"群组 ID：{code(gid)}\n"
                                  f"状态：{code('自动退出并清空数据')}\n"
                                  f"原因：{code('非管理员或已不在群组中')}\n")
                    thread(send_message, (client, glovar.debug_channel_id, debug_text))
            except Exception as e:
                logger.warning(f"Update admin in {gid} error: {e}", exc_info=True)
            finally:
                glovar.locks["admin"].release()

    return True


def update_status(client: Client) -> bool:
    # Update running status to BACKUP
    try:
        share_data(
            client=client,
            receivers=["BACKUP"],
            action="backup",
            action_type="status",
            data="awake"
        )

        return True
    except Exception as e:
        logger.warning(f"Update status error: {e}", exc_info=True)

    return False