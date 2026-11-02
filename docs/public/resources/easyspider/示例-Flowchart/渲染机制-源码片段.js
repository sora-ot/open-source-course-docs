// 由生成渲染演示.py从FlowChart.js提取；请修改原文件后重新生成。
// 两个函数的函数体保持原样；教学页另行提供app、LANG和bindEvents。

function newNode(node) {
    id = node["id"];
    title = node["title"];
    type = node["type"];
    if (type == 0) //顺序
    {
        return `<div class="sequence"><div class="node clk" draggable="true" data="${id}" dataType=${type} id = "${id}" position=${node["position"]} pId=${node["parentId"]}>
                <div >
                    <p style="margin-top: 2px">${title}</p>
                </div>
            </div>
            <p class="arrow" draggable="true" position=${node["position"]} data = "${id}" pId=${node["parentId"]}>↓</p></div>`;
    } else if (type == 1) //循环
    {
        return `<div class="loop clk" data="${id}" draggable="true" dataType=${type} id = "${id}" position=${node["position"]} pId=${node["parentId"]}>
             <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">${title}</p>
                <p class="arrow" draggable="true" position=-1 data = "${id}" pId=${id}>↓</p>
            </div>
            <p class="arrow" draggable="true" data = "${id}" position=${node["position"]} pId=${node["parentId"]}>↓</p></div>`;
    } else if (type == 2) //判断
    {
        return LANG(`<div class="loop clk" draggable="true" dataType=${type} data="${id}" position=${node["position"]} pId=${node["parentId"]}>
                    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">${title}</p>
                    <p class="branchAdd" data="${id}">点击此处在最右边增加条件分支</p>
                    <div class="judge" id = "${id}">
                    </div></div>
                    <p class="arrow" draggable="true" data = "${id}" position=${node["position"]} pId=${node["parentId"]}>↓</p></div>`,
            `<div class="loop clk" draggable="true" dataType=${type} data="${id}" position=${node["position"]} pId=${node["parentId"]}>
                    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">${title}</p>
                    <p class="branchAdd" data="${id}">Click here to add a new condition to the right most</p>
                    <div class="judge" id = "${id}">
                    </div></div>
                    <p class="arrow" draggable="true" data = "${id}" position=${node["position"]} pId=${node["parentId"]}>↓</p></div>`);
    } else //判断分支
    {
        return `<div class="branch clk" dataType=${type} data="${id}" position=${node["position"]} pId=${node["parentId"]}>
                    <p style="background:#d6d6d6;text-align:left;padding: 2px 2px 2px 5px">${title}</p>
                    <p data = "${id}" class="arrow" draggable="true" position=-1 pId=${id}>↓</p>
                    <div id = "${id}">
                    </div></div>`;
    }
}

function refresh(nowArrowReset = true) {
    $("#0").empty();
    $("#0").append(`<div style="border-radius: 50%;width: 40px;height: 40px;border:solid;border-color:seagreen;margin:5px auto;background-color:lightcyan;margin-top:20px">
                        <p style="font-size: 24px!important;text-align: center;margin-left: 6px;font-family:'Times New Roman'">▶</p>
                        </div>
                        <p id="firstArrow" class="arrow" position=-1 pId=0>↓</p>`);
    actionSequence.splice(0);
    queue.splice(0);
    let idd = 1;
    queue.push(0);
    actionSequence.push(0);
    while (queue.length != 0) {
        let nd = queue.shift(); //取出父元素并建立对子元素的链接
        for (let i = 0; i < nodeList[nd].sequence.length; i++) {
            nodeList[nodeList[nd].sequence[i]].parentId = nodeList[nd].id;
            nodeList[nodeList[nd].sequence[i]]["position"] = i;
            nodeList[nodeList[nd].sequence[i]].id = idd++;
            //检测元素是否位于循环内
            if (nodeList[nd].option == 8 || nodeList[nd].isInLoop) {
                nodeList[nodeList[nd].sequence[i]].isInLoop = true;
            } else {
                nodeList[nodeList[nd].sequence[i]].isInLoop = false;
            }
            queue.push(nodeList[nd].sequence[i]);
            actionSequence.push(nodeList[nd].sequence[i]);
        }
    }
    if (nowArrowReset) //如果要重置锚点位置
    {
        app._data.nowArrow = {"position": nodeList[0].sequence.length - 1, "pId": 0, "num": 0}; //设置默认要添加的位置是元素流程最开头处
    }
    //第一个元素不渲染
    for (let i = 1; i < actionSequence.length; i++) {
        let parentId = nodeList[actionSequence[i]]["parentId"];
        $("#" + parentId).append(newNode(nodeList[actionSequence[i]]));
    }
    bindEvents();
}
